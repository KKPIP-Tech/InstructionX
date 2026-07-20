"""
GitHub 插件安装器

从 GitHub 仓库安装插件的核心逻辑，支持单插件和多插件仓库。
"""

import base64
import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from urllib.parse import urlparse

import requests

from utils.logging_tools import LoggerManager, get_name
from .dependency_manager import DependencyManager
# 无循环依赖（manager 不反向依赖本模块），置顶导入
from .manager import get_plugin_manager


@dataclass
class InstallResult:
    """插件安装结果"""
    success: bool = False
    message: str = ""
    plugin_id: Optional[str] = None
    plugin_name: Optional[str] = None

    @staticmethod
    def ok(plugin_id: str, plugin_name: str, message: str = "安装成功") -> "InstallResult":
        """构造成功结果（原名 success，与字段同名会产生冲突，故改名为 ok）"""
        return InstallResult(
            success=True,
            message=message,
            plugin_id=plugin_id,
            plugin_name=plugin_name
        )

    @staticmethod
    def error(message: str) -> "InstallResult":
        return InstallResult(success=False, message=message)


@dataclass
class PluginInfo:
    """插件信息（从描述文件读取）"""
    plugin_id: str
    name: str
    version: str
    main: str
    description: Optional[str] = None
    author: Optional[str] = None
    homepage: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    dependencies: Dict[str, str] = field(default_factory=dict)
    path: str = ""  # 相对于仓库根目录的路径


@dataclass
class RepoInspectionResult:
    """仓库检查结果"""
    repo_type: str  # "multi", "single", "invalid"
    plugins: List[PluginInfo] = field(default_factory=list)
    error_message: Optional[str] = None

    @staticmethod
    def multi(plugins: List[PluginInfo]) -> "RepoInspectionResult":
        return RepoInspectionResult(repo_type="multi", plugins=plugins)

    @staticmethod
    def single(plugin: PluginInfo) -> "RepoInspectionResult":
        return RepoInspectionResult(repo_type="single", plugins=[plugin])

    @staticmethod
    def invalid(message: str) -> "RepoInspectionResult":
        return RepoInspectionResult(repo_type="invalid", error_message=message)


class GitHubPluginInstaller:
    """
    从 GitHub 安装插件的安装器

    支持：
    - 单插件仓库（仓库根目录有 IXPlugin.json）
    - 多插件仓库（仓库根目录有 IXRepo.json）
    """

    PLUGIN_DESCRIPTOR_FILE = "IXPlugin.json"  # 单插件描述文件名
    REPO_INDEX_FILE = "IXRepo.json"          # 多插件仓库索引文件名
    KKPIP_TECH_ORG = "KKPIP-Tech"

    # 下载与解压的安全上限
    MAX_DOWNLOAD_SIZE = 200 * 1024 * 1024    # 仓库压缩包最大 200MB
    MAX_EXTRACT_FILE_SIZE = 100 * 1024 * 1024  # 单个解压文件最大 100MB
    MAX_EXTRACT_TOTAL_SIZE = 500 * 1024 * 1024  # 总解压大小最大 500MB
    MAX_EXTRACT_FILE_COUNT = 20000           # 解压文件数量上限

    # 网络请求与下载的超时/分块配置
    GITHUB_API_TIMEOUT = 30            # GitHub API 内容查询超时（秒）
    DEFAULT_BRANCH_TIMEOUT = 10        # 默认分支查询超时（秒）
    ARCHIVE_DOWNLOAD_TIMEOUT = 60      # 仓库压缩包下载超时（秒）
    DOWNLOAD_CHUNK_SIZE = 256 * 1024   # 流式下载分块大小（字节）

    def __init__(self, plugin_manager=None):
        self._plugin_manager = plugin_manager
        self._logger = LoggerManager()
        self._gh_api_base = "https://api.github.com"

    def _get_target_directory(self, owner: str, official_dir: Path, thirdparty_dir: Path) -> Tuple[Path, str]:
        """根据 owner 确定安装目录和类型描述"""
        if owner == self.KKPIP_TECH_ORG:
            return official_dir, "官方插件目录 (plugin/)"
        return thirdparty_dir, "第三方插件目录 (custom_plugin/)"

    def parse_github_url(self, url: str) -> Optional[Tuple[str, str]]:
        """
        解析 GitHub URL，返回 (owner, repo)

        支持格式:
        - https://github.com/owner/repo
        - https://github.com/owner/repo.git
        - https://github.com/owner/repo/releases
        - git@github.com:owner/repo.git
        """
        # 处理 SSH 格式
        if url.startswith("git@"):
            match = re.match(r"git@github\.com:([^/]+)/(.+?)(?:\.git)?$", url)
            if match:
                return match.group(1), match.group(2)

        # 处理 HTTPS 格式
        parsed = urlparse(url)
        if parsed.netloc in ("github.com", "www.github.com"):
            parts = parsed.path.strip("/").split("/")
            if len(parts) >= 2:
                # 去除 .git 后缀
                repo = parts[1]
                if repo.endswith(".git"):
                    repo = repo[:-4]
                return parts[0], repo

        return None

    def _fetch_file_content(self, owner: str, repo: str, file_path: str) -> Optional[Dict[str, Any]]:
        """通过 GitHub API 获取文件内容"""
        url = f"{self._gh_api_base}/repos/{owner}/{repo}/contents/{file_path}"
        try:
            response = requests.get(url, timeout=self.GITHUB_API_TIMEOUT)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict) and data.get("encoding") == "base64":
                    content = base64.b64decode(data["content"]).decode("utf-8")
                    return json.loads(content)
            return None
        except Exception as e:
            self._logger.warning(get_name(), f"Failed to fetch {file_path}: {e}")
            return None

    def _fetch_directory_contents(self, owner: str, repo: str, path: str = "") -> Optional[List[Dict]]:
        """通过 GitHub API 获取目录内容"""
        url = f"{self._gh_api_base}/repos/{owner}/{repo}/contents/{path}"
        try:
            response = requests.get(url, timeout=self.GITHUB_API_TIMEOUT)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            self._logger.warning(get_name(), f"Failed to fetch directory {path}: {e}")
            return None

    def inspect_repository(self, github_url: str) -> RepoInspectionResult:
        """
        检查仓库返回可安装的插件列表

        Returns:
            RepoInspectionResult: 包含：
            - repo_type: "multi", "single", 或 "invalid"
            - plugins: List[PluginInfo]
            - error_message: 如果无效
        """
        result = self.parse_github_url(github_url)
        if not result:
            return RepoInspectionResult.invalid("无效的 GitHub URL 格式")

        owner, repo = result

        # 1. 优先检查 IXRepo.json（多插件仓库）
        repo_index = self._fetch_file_content(owner, repo, self.REPO_INDEX_FILE)
        if repo_index:
            return self._parse_multi_plugin_repo(repo_index, owner, repo)

        # 2. 检查 IXPlugin.json（单插件仓库）
        plugin_desc = self._fetch_file_content(owner, repo, self.PLUGIN_DESCRIPTOR_FILE)
        if plugin_desc:
            return self._parse_single_plugin_repo(plugin_desc, "")

        # 3. 都没有，返回无效
        return RepoInspectionResult.invalid(
            "该仓库不包含有效的插件描述文件 (IXPlugin.json 或 IXRepo.json)"
        )

    def _parse_multi_plugin_repo(
        self, repo_index: Dict[str, Any], owner: str, repo: str
    ) -> RepoInspectionResult:
        """解析多插件仓库索引"""
        plugins = []
        for entry in repo_index.get("plugins", []):
            path = entry.get("path", "")
            plugin_id = entry.get("id", "")

            # 获取每个插件的描述文件
            desc_path = f"{path}/{self.PLUGIN_DESCRIPTOR_FILE}" if path else self.PLUGIN_DESCRIPTOR_FILE
            plugin_desc = self._fetch_file_content(owner, repo, desc_path)

            if plugin_desc:
                plugin_info = self._parse_plugin_descriptor(plugin_desc, path)
                plugins.append(plugin_info)
            else:
                # 如果没有描述文件，用索引中的基本信息创建
                plugins.append(PluginInfo(
                    plugin_id=plugin_id,
                    name=entry.get("name", plugin_id),
                    version="unknown",
                    main="entrance.py",
                    path=path
                ))

        if not plugins:
            return RepoInspectionResult.invalid("IXRepo.json 中没有找到有效的插件")

        return RepoInspectionResult.multi(plugins)

    def _parse_single_plugin_repo(self, plugin_desc: Dict[str, Any], path: str) -> RepoInspectionResult:
        """解析单插件仓库"""
        plugin_info = self._parse_plugin_descriptor(plugin_desc, path)
        return RepoInspectionResult.single(plugin_info)

    def _parse_plugin_descriptor(self, desc: Dict[str, Any], path: str) -> PluginInfo:
        """解析插件描述文件"""
        return PluginInfo(
            plugin_id=desc.get("id", ""),
            name=desc.get("name", "Unknown"),
            version=desc.get("version", "release.0.0.0"),
            main=desc.get("main", "entrance.py"),
            description=desc.get("description"),
            author=desc.get("author"),
            homepage=desc.get("homepage"),
            keywords=desc.get("keywords", []),
            dependencies=desc.get("dependencies", {}),
            path=path
        )

    def validate_descriptor(self, descriptor: Dict[str, Any]) -> Tuple[bool, str]:
        """
        验证描述文件格式

        Returns:
            (is_valid, error_message)
        """
        required_fields = ["id", "name", "version", "main"]
        for field_name in required_fields:
            if field_name not in descriptor:
                return False, f"缺少必需字段: {field_name}"

        # 验证 version 格式
        version = descriptor.get("version", "")
        if not re.match(r"^(release|pre-release|beta|alpha|internal)\.\d+\.\d+\.\d+$", version):
            return False, f"版本号格式无效: {version}，期望格式: <类型>.<大>.<小>.<补丁>"

        # 验证 id 格式
        plugin_id = descriptor.get("id", "")
        if not re.match(r"^[a-zA-Z0-9_-]+$", plugin_id):
            return False, f"插件 ID 格式无效: {plugin_id}"

        return True, ""

    def install_from_url(
        self,
        github_url: str,
        selected_plugins: List[str] = None,
        official_dir: Path = None,
        thirdparty_dir: Path = None,
        progress_callback=None
    ) -> List[InstallResult]:
        """
        从 GitHub URL 安装插件

        Args:
            github_url: GitHub 仓库 URL
            selected_plugins: 要安装的插件路径列表（相对于仓库根目录）
                            为 None 时安装所有插件
            official_dir: 官方插件目录
            thirdparty_dir: 第三方插件目录

        Returns:
            List[InstallResult]: 每个插件的安装结果
        """
        result = self.parse_github_url(github_url)
        if not result:
            return [InstallResult.error("无效的 GitHub URL 格式")]

        owner, repo = result

        # 确定安装目录
        if official_dir is None or thirdparty_dir is None:
            pm = self._plugin_manager or get_plugin_manager()
            official_dir = pm.official_plugin_dir
            thirdparty_dir = pm.thirdparty_plugin_dir

        target_dir, dir_desc = self._get_target_directory(owner, official_dir, thirdparty_dir)

        # 下载仓库到临时目录
        temp_dir = self._download_repository(owner, repo)
        if temp_dir is None:
            return [InstallResult.error("下载仓库失败")]

        try:
            # 优先检查多插件仓库
            repo_index_path = temp_dir / self.REPO_INDEX_FILE
            if repo_index_path.exists():
                return self._install_from_multi_plugin_repo(
                    repo_index_path, target_dir, selected_plugins, dir_desc, progress_callback
                )
            else:
                # 单插件仓库
                plugin_path = temp_dir / self.PLUGIN_DESCRIPTOR_FILE
                if not plugin_path.exists():
                    return [InstallResult.error("插件描述文件不存在")]

                return self._install_single_plugin(temp_dir, target_dir, dir_desc, progress_callback)
        finally:
            # 清理临时目录
            self._cleanup_temp_dir(temp_dir)

    def _get_default_branch(self, owner: str, repo: str) -> Optional[str]:
        """通过 GitHub API 获取仓库默认分支

        无认证、短超时请求；失败时静默返回 None，由调用方回退 main→master。
        """
        try:
            response = requests.get(
                f"{self._gh_api_base}/repos/{owner}/{repo}",
                timeout=self.DEFAULT_BRANCH_TIMEOUT
            )
            if response.status_code == 200:
                branch = response.json().get("default_branch")
                if branch:
                    return branch
        except Exception as e:
            # 网络失败/限流时回退 main→master，不影响主流程
            self._logger.debug(get_name(), f"获取默认分支失败，回退 main/master: {e}")
        return None

    def _download_repository(self, owner: str, repo: str) -> Optional[Path]:
        """下载整个仓库到临时目录（流式下载 + 安全解压）"""
        temp_dir = None
        completed = False
        try:
            # 创建临时目录
            temp_dir = Path(tempfile.mkdtemp(prefix=f"ix_plugin_{repo}_"))

            # 优先查询默认分支，失败时回退依次尝试 main、master
            default_branch = self._get_default_branch(owner, repo)
            candidate_branches = [default_branch] if default_branch else ["main", "master"]

            response = None
            last_status = None
            for branch in candidate_branches:
                archive_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"
                try:
                    resp = requests.get(
                        archive_url, timeout=self.ARCHIVE_DOWNLOAD_TIMEOUT, stream=True
                    )
                except Exception as e:
                    self._logger.error(get_name(), f"Error downloading repository: {e}")
                    return None
                if resp.status_code == 200:
                    response = resp
                    break
                last_status = resp.status_code
                resp.close()
                if resp.status_code != 404:
                    break

            if response is None:
                self._logger.error(get_name(), f"Failed to download repo: {last_status}")
                return None

            # 流式写入临时 zip 文件，避免整包读入内存，并限制下载大小
            zip_path = temp_dir / "__repo_archive__.zip"
            downloaded = 0
            with response, open(zip_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=self.DOWNLOAD_CHUNK_SIZE):
                    if not chunk:
                        continue
                    downloaded += len(chunk)
                    if downloaded > self.MAX_DOWNLOAD_SIZE:
                        self._logger.error(
                            get_name(),
                            f"仓库压缩包超过大小上限 ({self.MAX_DOWNLOAD_SIZE // (1024 * 1024)}MB)"
                        )
                        return None
                    f.write(chunk)

            # 安全解压（zip-slip 校验 + 大小/数量限制）
            if not self._safe_extract_zip(zip_path, temp_dir):
                return None

            # 解压成功后删除压缩包
            try:
                zip_path.unlink()
            except OSError:
                pass

            completed = True
            return temp_dir

        except Exception as e:
            self._logger.error(get_name(), f"Error downloading repository: {e}")
            return None
        finally:
            # 所有失败路径都要清理临时目录（成功路径由调用方负责清理）
            if not completed and temp_dir is not None and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _safe_extract_zip(self, zip_path: Path, temp_dir: Path) -> bool:
        """安全解压仓库 zip 到临时目录

        防护：
        - zip-slip：逐个 entry 校验 resolve 后的路径必须位于目标目录内
        - 单文件大小、总解压大小、文件数量限制
        """
        try:
            with zipfile.ZipFile(zip_path) as zf:
                all_names = zf.namelist()
                if not all_names:
                    return False

                # 找到根目录（通常是 repo-<branch>）
                root_prefix = all_names[0].split("/")[0] + "/"
                dest_root = temp_dir.resolve()

                total_size = 0
                file_count = 0
                for info in zf.infolist():
                    name = info.filename
                    if not name.startswith(root_prefix):
                        continue
                    target_name = name[len(root_prefix):]
                    if not target_name:
                        continue

                    # zip-slip 校验：解析后的绝对路径必须位于目标目录内
                    target_path = (temp_dir / target_name).resolve()
                    if target_path != dest_root and dest_root not in target_path.parents:
                        self._logger.error(get_name(), f"拒绝解压越界路径: {name}")
                        return False

                    if name.endswith("/"):
                        target_path.mkdir(parents=True, exist_ok=True)
                        continue

                    file_count += 1
                    if file_count > self.MAX_EXTRACT_FILE_COUNT:
                        self._logger.error(
                            get_name(),
                            f"解压文件数量超过上限 ({self.MAX_EXTRACT_FILE_COUNT})"
                        )
                        return False
                    if info.file_size > self.MAX_EXTRACT_FILE_SIZE:
                        self._logger.error(
                            get_name(),
                            f"文件 {name} 超过单文件大小上限 ({self.MAX_EXTRACT_FILE_SIZE // (1024 * 1024)}MB)"
                        )
                        return False
                    total_size += info.file_size
                    if total_size > self.MAX_EXTRACT_TOTAL_SIZE:
                        self._logger.error(
                            get_name(),
                            f"解压总大小超过上限 ({self.MAX_EXTRACT_TOTAL_SIZE // (1024 * 1024)}MB)"
                        )
                        return False

                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as src, open(target_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)

            return True
        except Exception as e:
            self._logger.error(get_name(), f"解压仓库失败: {e}")
            return False

    def _install_from_multi_plugin_repo(
        self,
        repo_index_path: Path,
        target_dir: Path,
        selected_plugins: List[str],
        dir_desc: str,
        progress_callback=None
    ) -> List[InstallResult]:
        """从多插件仓库安装"""
        try:
            with open(repo_index_path, "r", encoding="utf-8") as f:
                repo_index = json.load(f)
        except Exception as e:
            return [InstallResult.error(f"读取仓库索引失败: {e}")]

        results = []
        plugins_list = repo_index.get("plugins", [])
        repo_root = repo_index_path.parent.resolve()

        for plugin_entry in plugins_list:
            plugin_path_str = plugin_entry.get("path", "")
            plugin_id = plugin_entry.get("id", "")

            # 如果用户指定了插件，检查是否在列表中
            if selected_plugins is not None and plugin_path_str not in selected_plugins:
                continue

            # 路径穿越防护：解析后的插件目录必须位于仓库根目录内
            plugin_dir = (repo_index_path.parent / plugin_path_str).resolve()
            if plugin_dir != repo_root and repo_root not in plugin_dir.parents:
                results.append(InstallResult.error(f"插件路径越出仓库根目录，已拒绝: {plugin_path_str}"))
                continue

            if not plugin_dir.exists():
                results.append(InstallResult.error(f"插件目录不存在: {plugin_path_str}"))
                continue

            result = self._install_plugin_dir(plugin_dir, target_dir, plugin_id, dir_desc, progress_callback)
            results.append(result)

        return results

    def _install_single_plugin(
        self,
        plugin_root: Path,
        target_dir: Path,
        dir_desc: str,
        progress_callback=None
    ) -> List[InstallResult]:
        """安装单插件仓库（插件文件直接在仓库根目录）"""
        return self._install_plugin_dir(plugin_root, target_dir, "", dir_desc, progress_callback)

    def _install_plugin_dir(
        self,
        plugin_dir: Path,
        target_dir: Path,
        plugin_id: str = "",
        dir_desc: str = "",
        progress_callback=None
    ) -> InstallResult:
        """安装单个插件目录"""
        try:
            # 读取插件描述文件
            desc_file = plugin_dir / self.PLUGIN_DESCRIPTOR_FILE
            if not desc_file.exists():
                return InstallResult.error(f"插件目录中没有找到 {self.PLUGIN_DESCRIPTOR_FILE}")

            try:
                with open(desc_file, "r", encoding="utf-8") as f:
                    descriptor = json.load(f)
            except Exception as e:
                return InstallResult.error(f"读取插件描述文件失败: {e}")

            # 验证描述文件
            is_valid, error_msg = self.validate_descriptor(descriptor)
            if not is_valid:
                return InstallResult.error(f"插件描述文件无效: {error_msg}")

            # 获取插件 ID 和名称
            actual_plugin_id = descriptor.get("id", plugin_id)
            plugin_name = descriptor.get("name", "Unknown")

            # 检查并安装插件依赖
            dependencies = descriptor.get("dependencies", {})
            if dependencies:
                dep_mgr = DependencyManager()
                check_result = dep_mgr.check_dependencies(dependencies)
                if not check_result.satisfied:
                    missing = check_result.missing
                    msg = f"插件 {actual_plugin_id} 缺少依赖: {', '.join(missing)}，正在自动安装..."
                    self._logger.info(get_name(), msg)
                    if progress_callback:
                        progress_callback(msg)
                    install_result = dep_mgr.install_dependencies(dependencies)
                    if not install_result.success:
                        return InstallResult.error(f"依赖安装失败: {install_result.message}")
                    msg = f"插件 {actual_plugin_id} 依赖安装完成"
                    self._logger.info(get_name(), msg)
                    if progress_callback:
                        progress_callback(msg)

            # 确定目标目录
            target_plugin_dir = target_dir / actual_plugin_id
            backup_dir = target_dir / f"{actual_plugin_id}.bak"

            # 升级回滚保护：旧版本先重命名为 .bak，安装成功后再删除，失败时恢复
            if target_plugin_dir.exists():
                if backup_dir.exists():
                    shutil.rmtree(backup_dir, ignore_errors=True)
                shutil.move(str(target_plugin_dir), str(backup_dir))

            # 创建目标目录
            target_dir.mkdir(parents=True, exist_ok=True)

            try:
                # 复制插件文件
                shutil.copytree(plugin_dir, target_plugin_dir)

                # 确保 __init__.py 存在
                init_file = target_plugin_dir / "__init__.py"
                if not init_file.exists():
                    init_file.write_text("")
            except Exception:
                # 安装失败：清理半成品目录并从 .bak 恢复旧版本
                if target_plugin_dir.exists():
                    shutil.rmtree(target_plugin_dir, ignore_errors=True)
                if backup_dir.exists():
                    shutil.move(str(backup_dir), str(target_plugin_dir))
                raise

            # 安装成功，删除旧版本备份
            if backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)

            self._logger.info(get_name(), f"插件已安装到 {target_plugin_dir}")
            return InstallResult.ok(actual_plugin_id, plugin_name, f"安装成功 ({dir_desc})")

        except Exception as e:
            self._logger.error(get_name(), f"安装插件失败: {e}")
            return InstallResult.error(f"安装插件失败: {e}")

    def _cleanup_temp_dir(self, temp_dir: Path):
        """清理临时目录"""
        try:
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            self._logger.warning(get_name(), f"清理临时目录失败: {e}")
