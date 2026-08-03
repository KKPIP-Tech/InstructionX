"""
插件依赖管理器

负责检查和自动安装插件所需的 Python 依赖。
"""

import importlib.metadata
import shutil
import subprocess
import sys
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Callable

from packaging.specifiers import SpecifierSet, InvalidSpecifier
from packaging.version import Version, InvalidVersion

from utils.logging_tools import LoggerManager, get_name


@dataclass
class DependencyCheckResult:
    """依赖检查结果"""
    satisfied: bool  # 所有依赖是否已满足
    missing: List[str]  # 缺失的依赖包名列表（不含版本约束）


@dataclass
class DependencyInstallResult:
    """依赖安装结果"""
    success: bool
    message: str = ""
    failed_packages: List[str] = None  # 安装失败的包名列表

    def __post_init__(self):
        if self.failed_packages is None:
            self.failed_packages = []


class DependencyManager:
    """
    插件依赖管理器

    负责：
    - 检查插件依赖是否满足
    - 自动安装缺失的依赖（优先使用 uv，uv 不可用时回退到 pip）
    """

    # pip 子进程超时（秒）
    PIP_SHOW_TIMEOUT = 30
    PIP_INSTALL_TIMEOUT = 300

    # 包名白名单：PEP 508 名称字符集（[A-Za-z0-9._-]+），支持 extras 语法（如 uv[standard]）
    _PACKAGE_NAME_PATTERN = re.compile(r'^[A-Za-z0-9._-]+(\[[A-Za-z0-9._-]+(,[A-Za-z0-9._-]+)*\])?$')
    # 单个版本子约束白名单：比较符 + 版本号（可选 .* 后缀），与
    # _check_version_constraint 的解析能力对齐
    _SUB_CONSTRAINT_PATTERN = re.compile(r'^(>=|<=|==|!=|>|<)\s*\d+(?:\.\d+)*(?:\.\*)?$')

    def __init__(self):
        self._logger = LoggerManager()

    def _is_valid_install_input(self, package: str, version_constraint: str) -> bool:
        """校验待安装的包名与版本约束，防止注入 pip 命令行参数

        包名必须匹配 PEP 508 名称字符集（支持 [extras] 语法）且不以 '-' 开头；
        版本约束只接受逗号分隔的版本比较子约束（比较符/数字/点/星号/空白），
        任何含多 token、URL scheme 或其他字符的输入一律拒绝。

        Args:
            package: 包名
            version_constraint: 版本约束（可为空字符串）

        Returns:
            输入合法返回 True；非法时记 ERROR 日志并返回 False
        """
        if not package or not self._PACKAGE_NAME_PATTERN.match(package) or package.startswith('-'):
            self._logger.error(get_name(), f"拒绝非法依赖包名（可能存在参数注入）: {package!r}")
            return False

        if not version_constraint:
            return True

        # 约束串只允许版本比较符/数字/点/逗号/星号与空白组成子约束；
        # ':'、'/'、'-' 等字符（URL scheme、pip 参数）不在白名单内，天然被拒绝
        parts = [part.strip() for part in version_constraint.split(',')]
        if not parts or any(not self._SUB_CONSTRAINT_PATTERN.match(part) for part in parts):
            self._logger.error(
                get_name(),
                f"拒绝非法版本约束（可能存在参数注入）: {package!r} {version_constraint!r}"
            )
            return False
        return True

    def check_dependencies(self, dependencies: Dict[str, str]) -> DependencyCheckResult:
        """
        检查依赖是否满足

        Args:
            dependencies: 依赖字典，key 为包名，value 为版本约束
                         例如: {"requests": ">=2.25.0", "numpy": ""}

        Returns:
            DependencyCheckResult: 包含是否满足和缺失列表
        """
        if not dependencies:
            return DependencyCheckResult(satisfied=True, missing=[])

        missing = []
        for package, version_constraint in dependencies.items():
            if not self._is_package_installed(package, version_constraint):
                missing.append(package)

        return DependencyCheckResult(
            satisfied=len(missing) == 0,
            missing=missing
        )

    def get_missing_dependencies(self, dependencies: Dict[str, str]) -> List[str]:
        """
        获取缺失的依赖包名列表

        Args:
            dependencies: 依赖字典

        Returns:
            缺失的包名列表（不含版本约束）
        """
        result = self.check_dependencies(dependencies)
        return result.missing

    def install_dependencies(
        self,
        dependencies: Dict[str, str],
        callback: Optional[Callable[[str], None]] = None
    ) -> DependencyInstallResult:
        """
        安装缺失的依赖

        Args:
            dependencies: 依赖字典，key 为包名，value 为版本约束
            callback: 可选的进度回调，接收安装消息字符串

        Returns:
            DependencyInstallResult: 安装结果
        """
        if not dependencies:
            return DependencyInstallResult(success=True, message="无依赖需要安装")

        check_result = self.check_dependencies(dependencies)
        if check_result.satisfied:
            return DependencyInstallResult(success=True, message="所有依赖已满足")

        # 需要安装的依赖（先对包名与版本约束做白名单校验，非法项跳过不中断其他包）
        to_install = []
        for package, version_constraint in dependencies.items():
            if package not in check_result.missing:
                continue
            if not self._is_valid_install_input(package, version_constraint):
                continue
            if version_constraint:
                to_install.append(f"{package}{version_constraint}")
            else:
                to_install.append(package)

        if not to_install:
            return DependencyInstallResult(
                success=False,
                message="缺失依赖均未通过安装前的安全校验，未执行安装"
            )

        if callback:
            callback(f"开始安装依赖: {', '.join(to_install)}")

        # 透明化：pip install 可安装任意包（插件系统设计使然），安装前记录清单
        self._logger.warning(
            get_name(),
            f"即将通过 pip 安装插件声明的依赖包: {', '.join(to_install)}"
        )

        failed_packages = []

        for package_spec in to_install:
            if callback:
                callback(f"正在安装 {package_spec}...")

            success = self._install_package(package_spec)
            if not success:
                failed_packages.append(package_spec)
                msg = f"安装失败: {package_spec}"
                if callback:
                    callback(msg)
                self._logger.error(get_name(), msg)
            else:
                msg = f"已安装: {package_spec}"
                if callback:
                    callback(msg)
                self._logger.info(get_name(), msg)

        if failed_packages:
            return DependencyInstallResult(
                success=False,
                message=f"部分依赖安装失败: {', '.join(failed_packages)}",
                failed_packages=failed_packages
            )

        return DependencyInstallResult(
            success=True,
            message=f"成功安装 {len(to_install)} 个依赖包"
        )

    def _is_package_installed(self, package: str, version_constraint: str) -> bool:
        """
        检查包是否已安装且满足版本约束

        Args:
            package: 包名
            version_constraint: 版本约束，如 ">=2.25.0" 或空字符串

        Returns:
            bool: 是否满足
        """
        try:
            # 获取已安装版本：优先 importlib.metadata（避免每包一次 pip show 子进程），
            # 查不到时回退 pip show（兼容 importlib.metadata 不可见的特殊安装方式）
            installed_version = self._get_installed_version(package)
            if installed_version is None:
                return False

            # 如果没有版本约束，包存在即可
            if not version_constraint:
                return True

            # 检查版本约束
            return self._check_version_constraint(installed_version, version_constraint)

        except subprocess.TimeoutExpired:
            self._logger.warning(get_name(), f"检查包 {package} 超时")
            return False
        except Exception as e:
            self._logger.warning(get_name(), f"检查包 {package} 时出错: {e}")
            return False

    def _get_installed_version(self, package: str) -> Optional[str]:
        """获取已安装包的版本号

        优先使用 importlib.metadata（进程内查询，无子进程开销）；
        包不存在或查询失败时回退 python -m pip show。
        """
        try:
            return importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            pass
        except Exception as e:
            # importlib.metadata 查询异常时回退 pip show，不影响主流程
            self._logger.debug(get_name(), f"importlib.metadata 查询 {package} 失败，回退 pip show: {e}")

        # 回退：使用 python -m pip show 检查包是否已安装
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", package],
            capture_output=True,
            text=True,
            timeout=self.PIP_SHOW_TIMEOUT
        )

        if result.returncode != 0:
            return None

        return self._parse_version_from_pip_show(result.stdout)

    def _parse_version_from_pip_show(self, output: str) -> Optional[str]:
        """从 pip show 输出中解析版本号"""
        for line in output.splitlines():
            if line.startswith("Version:"):
                return line.split(":", 1)[1].strip()
        return None

    def _check_version_constraint(self, installed_version: str, constraint: str) -> bool:
        """
        检查已安装版本是否满足版本约束

        支持逗号分隔的复合约束（如 ">=1.0,<2.0"），
        每个子约束的操作符限定为 >=、>、<=、<、==、!=。

        Args:
            installed_version: 已安装的版本，如 "2.26.0"
            constraint: 版本约束，如 ">=2.25.0"

        Returns:
            bool: 是否满足
        """
        # 规范化已安装版本（去除 pre-release、post-release 等后缀，仅保留 release 段）
        installed = self._normalize_version(installed_version)
        if installed is None:
            return False

        # 逐段解析复合约束，使用 packaging.specifiers.SpecifierSet 求值
        normalized_specs = []
        for part in constraint.split(","):
            part = part.strip()
            match = re.match(r'^(>=|<=|==|!=|>|<)\s*(\d+(?:\.\d+)*)$', part)
            if not match:
                # 无法解析的约束，默认不满足
                self._logger.warning(get_name(), f"无法解析版本约束: {constraint}")
                return False
            op = match.group(1)
            required = self._normalize_version(match.group(2))
            if required is None:
                self._logger.warning(get_name(), f"无法解析版本约束: {constraint}")
                return False
            normalized_specs.append(f"{op}{required}")

        try:
            spec_set = SpecifierSet(",".join(normalized_specs))
            return Version(installed) in spec_set
        except (InvalidSpecifier, InvalidVersion) as e:
            self._logger.warning(get_name(), f"无法解析版本约束: {constraint} ({e})")
            return False

    def _normalize_version(self, version: str) -> Optional[str]:
        """将版本号规范化为 release 段（如 '1.0.0a1' → '1.0.0'）

        基于 packaging.version.Version 解析，无法解析时返回 None。
        """
        try:
            return ".".join(str(p) for p in Version(version).release)
        except InvalidVersion:
            return None

    def _install_package(self, package_spec: str) -> bool:
        """
        安装单个依赖包

        优先尝试使用 uv 安装，uv 不可用或 uv 安装失败时回退到 pip。

        Args:
            package_spec: 包规格，如 "requests>=2.25.0" 或 "numpy"

        Returns:
            bool: 是否成功
        """
        uv_path = self._find_uv_executable()
        if uv_path and self._uv_install(uv_path, package_spec):
            return True
        if uv_path:
            self._logger.warning(get_name(), f"uv 安装 {package_spec} 失败，回退到 pip")
        return self._pip_install(package_spec)

    def _find_uv_executable(self) -> Optional[str]:
        """
        查找 uv 可执行文件

        优先在 PATH 中查找；未找到时回退到项目 .venv/Scripts/uv.exe（Windows）。
        """
        uv_path = shutil.which("uv")
        if uv_path:
            return uv_path
        project_root = Path(__file__).parent.parent.parent
        venv_uv = project_root / ".venv" / "Scripts" / "uv.exe"
        if venv_uv.exists():
            return str(venv_uv)
        return None

    def _uv_install(self, uv_path: str, package_spec: str) -> bool:
        """
        使用 uv 安装包

        通过 --python 指定当前解释器，确保安装到当前虚拟环境。
        """
        try:
            result = subprocess.run(
                [uv_path, "pip", "install", "--python", sys.executable, package_spec],
                capture_output=True,
                text=True,
                timeout=self.PIP_INSTALL_TIMEOUT
            )
            if result.returncode != 0:
                self._logger.error(get_name(), f"uv install {package_spec} 失败: {result.stderr.strip()}")
                return False
            return True
        except subprocess.TimeoutExpired:
            self._logger.error(get_name(), f"uv install {package_spec} 超时")
            return False
        except Exception as e:
            self._logger.error(get_name(), f"uv install {package_spec} 出错: {e}")
            return False

    def _pip_install(self, package_spec: str) -> bool:
        """
        使用 pip 安装包（uv 不可用时的回退）

        Args:
            package_spec: 包规格，如 "requests>=2.25.0" 或 "numpy"

        Returns:
            bool: 是否成功
        """
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", package_spec, "--quiet"],
                capture_output=True,
                text=True,
                timeout=self.PIP_INSTALL_TIMEOUT
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                self._logger.error(get_name(), f"pip install {package_spec} 失败: {error_msg}")
                return False

            return True

        except subprocess.TimeoutExpired:
            self._logger.error(get_name(), f"pip install {package_spec} 超时")
            return False
        except Exception as e:
            self._logger.error(get_name(), f"pip install {package_spec} 出错: {e}")
            return False
