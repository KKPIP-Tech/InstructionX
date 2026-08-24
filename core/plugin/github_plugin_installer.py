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
from typing import List, Optional, Tuple, Dict, Any, Union
from urllib.parse import urlparse

import requests

from core.i18n import DEFAULT_LANGUAGE, I18nSettingsStore, resolve_i18n_field
from utils.logging_tools import LoggerManager, get_name
from .dependency_manager import DependencyManager
# 无循环依赖（manager 不反向依赖本模块），置顶导入
from .manager import get_plugin_manager
from .plugin_identity import PluginIdentity
from .plugin_version import PluginVersion


@dataclass
class InstallResult:
    """插件安装结果"""
    success: bool = False
    message: str = ""
    plugin_id: Optional[str] = None
    plugin_name: Optional[str] = None
    relation: str = ""  # new / upgrade / downgrade / reinstall

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


# 可多语言字段的原始形式：纯字符串（旧形式）或 {语言代码: 文案} 字典（§10.4b）
I18nFieldValue = Union[str, Dict[str, str]]


@dataclass
class PluginInfo:
    """插件信息（从描述文件读取）

    name/description 保留描述文件中的原始形式（纯字符串或多语言字典），
    不做语言解析——解析发生在展示层（安装对话框），避免丢失其他语言文案。
    """
    plugin_id: str
    name: I18nFieldValue
    version: str
    main: str
    description: Optional[I18nFieldValue] = None
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


@dataclass
class ReleaseInfo:
    """GitHub Release 版本信息（用于升级/降级选择）"""
    tag: str
    name: str
    version: str = ""          # 从 IXPlugin.json 解析的插件版本，解析失败为空
    prerelease: bool = False
    published_at: str = ""


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
    RELEASES_PER_PAGE = 30             # 查询 Release 列表的单页数量

    # GitHub Token 环境变量（可选，用于提升 API 限流阈值/访问私有仓库）
    GITHUB_TOKEN_ENV = "INSTRUCTIONX_GITHUB_TOKEN"

    def __init__(self, plugin_manager=None):
        self._plugin_manager = plugin_manager
        self._logger = LoggerManager()
        self._gh_api_base = "https://api.github.com"

    def _get_target_directory(self, owner: str, official_dir: Path, thirdparty_dir: Path) -> Tuple[Path, str]:
        """根据 owner 确定安装目录和类型描述（GitHub 用户名大小写不敏感）"""
        if owner.lower() == self.KKPIP_TECH_ORG.lower():
            return official_dir, "官方插件目录 (plugin/)"
        return thirdparty_dir, "第三方插件目录 (custom_plugin/)"

    def _current_language(self) -> str:
        """读取框架当前语言（纯 Python 配置读取，可在安装工作线程安全调用）

        读取失败时回退默认语言，不阻断安装流程。
        """
        try:
            settings = I18nSettingsStore().load_framework_settings()
            return settings.get("current_language") or DEFAULT_LANGUAGE
        except Exception as e:
            self._logger.warning(get_name(), f"读取当前语言失败，按默认语言解析: {e}")
            return DEFAULT_LANGUAGE

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

    def _github_headers(self) -> Dict[str, str]:
        """构造 GitHub API 请求头（存在 Token 环境变量时附带鉴权）"""
        token = os.environ.get(self.GITHUB_TOKEN_ENV, "").strip()
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    def _fetch_file_content(self, owner: str, repo: str, file_path: str,
                            ref: str = "") -> Optional[Dict[str, Any]]:
        """通过 GitHub API 获取文件内容，可选指定 ref（分支/tag）"""
        url = f"{self._gh_api_base}/repos/{owner}/{repo}/contents/{file_path}"
        params = {"ref": ref} if ref else None
        try:
            response = requests.get(url, headers=self._github_headers(),
                                    params=params, timeout=self.GITHUB_API_TIMEOUT)
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
            response = requests.get(url, headers=self._github_headers(),
                                    timeout=self.GITHUB_API_TIMEOUT)
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
        """解析插件描述文件（name/description 保留原始形式，可为多语言字典）"""
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
                    repo_index_path, target_dir, selected_plugins, dir_desc,
                    progress_callback, source_url=github_url
                )
            else:
                # 单插件仓库
                plugin_path = temp_dir / self.PLUGIN_DESCRIPTOR_FILE
                if not plugin_path.exists():
                    return [InstallResult.error("插件描述文件不存在")]

                return self._install_single_plugin(
                    temp_dir, target_dir, dir_desc, progress_callback, source_url=github_url
                )
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
                headers=self._github_headers(),
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
        """下载整个仓库到临时目录（依次尝试默认分支 / main / master）"""
        default_branch = self._get_default_branch(owner, repo)
        candidate_branches = [default_branch] if default_branch else ["main", "master"]

        last_status = None
        for branch in candidate_branches:
            archive_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"
            temp_dir, status = self._try_download_archive(archive_url, f"ix_plugin_{repo}_")
            if temp_dir is not None:
                return temp_dir
            last_status = status
            if status != 404:
                # 网络错误或非 404 状态码不再尝试其他分支
                break

        self._logger.error(get_name(), f"Failed to download repo: {last_status}")
        return None

    def _try_download_archive(self, archive_url: str, temp_prefix: str) -> Tuple[Optional[Path], Optional[int]]:
        """下载指定压缩包 URL 并安全解压到临时目录

        Args:
            archive_url: 仓库/Release 压缩包 URL
            temp_prefix: 临时目录名前缀

        Returns:
            (临时目录, None) 成功；(None, HTTP状态码) 请求失败；(None, None) 网络/解压错误
        """
        temp_dir = None
        completed = False
        try:
            temp_dir = Path(tempfile.mkdtemp(prefix=temp_prefix))
            try:
                response = requests.get(
                    archive_url, timeout=self.ARCHIVE_DOWNLOAD_TIMEOUT, stream=True
                )
            except Exception as e:
                self._logger.error(get_name(), f"Error downloading archive: {e}")
                return None, None

            if response.status_code != 200:
                status = response.status_code
                response.close()
                return None, status

            if not self._stream_to_zip(response, temp_dir):
                return None, None
            completed = True
            return temp_dir, None
        except Exception as e:
            self._logger.error(get_name(), f"Error downloading archive: {e}")
            return None, None
        finally:
            # 所有失败路径都要清理临时目录（成功路径由调用方负责清理）
            if not completed and temp_dir is not None and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _stream_to_zip(self, response, temp_dir: Path) -> bool:
        """流式写入压缩包并安全解压，成功时删除压缩包文件"""
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
                        f"压缩包超过大小上限 ({self.MAX_DOWNLOAD_SIZE // (1024 * 1024)}MB)"
                    )
                    return False
                f.write(chunk)

        # 安全解压（zip-slip 校验 + 大小/数量限制）
        if not self._safe_extract_zip(zip_path, temp_dir):
            return False

        try:
            zip_path.unlink()
        except OSError:
            pass
        return True

    def _safe_extract_zip(self, zip_path: Path, temp_dir: Path) -> bool:
        """安全解压仓库 zip 到临时目录

        防护：
        - zip-slip：逐个 entry 校验 resolve 后的路径必须位于目标目录内
        - 单文件大小、总解压大小、文件数量限制
        """
        try:
            with zipfile.ZipFile(zip_path) as zf:
                all_names = [n for n in zf.namelist() if n]
                if not all_names:
                    return False

                # 检测公共根目录（GitHub 压缩包通常是 repo-<branch>/；
                # 用户上传的 zip 可能没有公共根，此时不剥离任何前缀）
                roots = {n.split("/")[0] for n in all_names}
                root_prefix = roots.pop() + "/" if len(roots) == 1 else ""
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
        progress_callback=None,
        source_url: str = ""
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

            result = self._install_plugin_dir(
                plugin_dir, target_dir, plugin_id, dir_desc, progress_callback,
                source_type="github", source_url=source_url, source_path=plugin_path_str
            )
            results.append(result)

        return results

    def _install_single_plugin(
        self,
        plugin_root: Path,
        target_dir: Path,
        dir_desc: str,
        progress_callback=None,
        source_url: str = ""
    ) -> List[InstallResult]:
        """安装单插件仓库（插件文件直接在仓库根目录）"""
        return self._install_plugin_dir(
            plugin_root, target_dir, "", dir_desc, progress_callback,
            source_type="github", source_url=source_url
        )

    def _install_plugin_dir(
        self,
        plugin_dir: Path,
        target_dir: Path,
        plugin_id: str = "",
        dir_desc: str = "",
        progress_callback=None,
        source_type: str = "unknown",
        source_url: str = "",
        source_path: str = ""
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
            # name 允许 {语言代码: 文案} 字典形式（§10.4b）：注册表持久化与
            # InstallResult 需要字符串，这里解析为当前语言文案
            # （当前语言缺失时内部回退默认语言/字典首值）；
            # 目录名、版本比较等环节只使用 id/version，不受字典形式影响
            plugin_name = resolve_i18n_field(
                descriptor.get("name", "Unknown"), self._current_language())
            new_version = descriptor.get("version", "release.0.0.0")

            # 检测与已安装版本的关系（新装/升级/降级/重装）
            relation, prev_version = self._detect_install_relation(
                target_dir, actual_plugin_id, new_version
            )

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

                # 保留旧版本的插件 UUID 文件：覆盖/升级安装时 UUID 必须稳定，
                # 否则注册表、排序、分组、DataProvider 数据会与插件脱节
                backup_info = backup_dir / ".plugin_info.json"
                target_info = target_plugin_dir / ".plugin_info.json"
                if backup_info.exists() and not target_info.exists():
                    shutil.copy2(backup_info, target_info)
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

            # 登记版本注册表（供后续升级/降级与更新检查）
            self._record_install(
                target_dir, target_plugin_dir, actual_plugin_id, plugin_name,
                new_version, source_type, source_url, source_path
            )

            message = f"安装成功 ({dir_desc})"
            if relation != "new":
                label = {"upgrade": "升级", "downgrade": "降级", "reinstall": "重装"}[relation]
                message += f"（{label} {prev_version} → {new_version}）"

            self._logger.info(get_name(), f"插件已安装到 {target_plugin_dir}")
            result = InstallResult.ok(actual_plugin_id, plugin_name, message)
            result.relation = relation
            return result

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

    # ==================== 版本登记与关系检测 ====================

    def _scope_of_target_dir(self, target_dir: Path) -> str:
        """判断目标目录属于官方还是第三方插件目录"""
        pm = self._plugin_manager or get_plugin_manager()
        if Path(target_dir) == Path(pm.official_plugin_dir):
            return "official"
        return "thirdparty"

    def _detect_install_relation(self, target_dir: Path, descriptor_id: str,
                                 new_version: str) -> Tuple[str, str]:
        """检测本次安装与已安装版本的关系

        Returns:
            (relation, prev_version)：relation 为 new/upgrade/downgrade/reinstall
        """
        try:
            pm = self._plugin_manager or get_plugin_manager()
            scope = self._scope_of_target_dir(target_dir)
            found = pm.registry.find_by_descriptor(scope, descriptor_id)
        except Exception:
            return "new", ""
        if not found:
            return "new", ""

        prev_version = found[1].get("version", "")
        try:
            old_v = PluginVersion.from_string(prev_version)
            new_v = PluginVersion.from_string(new_version)
        except ValueError:
            return "reinstall", prev_version
        if new_v > old_v:
            return "upgrade", prev_version
        if new_v < old_v:
            return "downgrade", prev_version
        return "reinstall", prev_version

    def _record_install(self, target_dir: Path, target_plugin_dir: Path,
                        descriptor_id: str, plugin_name: str, version: str,
                        source_type: str, source_url: str, source_path: str) -> None:
        """安装成功后登记插件版本注册表

        通过 PluginIdentity 获取/生成稳定 UUID（与后续加载时一致），
        登记失败仅记录告警，不影响安装结果。
        """
        try:
            pm = self._plugin_manager or get_plugin_manager()
            scope = self._scope_of_target_dir(target_dir)
            # 优先复用注册表中已有 UUID（升级/重装场景），避免产生重复记录
            found = pm.registry.find_by_descriptor(scope, descriptor_id)
            if found:
                plugin_uuid = found[0]
            else:
                plugin_uuid = PluginIdentity(target_plugin_dir).load_or_create_id()
            pm.registry.upsert(
                plugin_uuid,
                descriptor_id=descriptor_id,
                name=plugin_name,
                scope=scope,
                version=version,
                source_type=source_type,
                source_url=source_url,
                source_path=source_path,
            )
        except Exception as e:
            self._logger.warning(get_name(), f"登记插件版本注册表失败: {e}")

    # ==================== 本地插件包安装 ====================

    def install_from_zip(
        self,
        zip_path,
        target_dir: Path = None,
        progress_callback=None
    ) -> List[InstallResult]:
        """从本地 zip 插件包安装/升级/降级插件

        Args:
            zip_path: 本地插件包路径（包含 IXPlugin.json 的 zip）
            target_dir: 目标目录；为 None 时自动判定（已安装同 id 插件则沿用其
                        目录，否则安装到第三方插件目录）
            progress_callback: 进度回调

        Returns:
            单元素 InstallResult 列表
        """
        zip_path = Path(zip_path)
        if not zip_path.exists():
            return [InstallResult.error(f"插件包不存在: {zip_path}")]

        temp_dir = Path(tempfile.mkdtemp(prefix="ix_plugin_zip_"))
        try:
            if not self._safe_extract_zip(zip_path, temp_dir):
                return [InstallResult.error("插件包解压失败或内容不安全")]

            plugin_root = self._locate_plugin_root(temp_dir)
            if plugin_root is None:
                return [InstallResult.error(f"插件包中未找到 {self.PLUGIN_DESCRIPTOR_FILE}")]

            target = Path(target_dir) if target_dir else self._resolve_zip_target_dir(plugin_root)
            return [self._install_plugin_dir(
                plugin_root, target, "", "本地插件包", progress_callback,
                source_type="local_zip"
            )]
        finally:
            self._cleanup_temp_dir(temp_dir)

    def _locate_plugin_root(self, temp_dir: Path) -> Optional[Path]:
        """在解压目录中定位插件根目录（包含 IXPlugin.json 的目录）"""
        if (temp_dir / self.PLUGIN_DESCRIPTOR_FILE).exists():
            return temp_dir
        subdirs = [p for p in temp_dir.iterdir() if p.is_dir()]
        if len(subdirs) == 1 and (subdirs[0] / self.PLUGIN_DESCRIPTOR_FILE).exists():
            return subdirs[0]
        return None

    def _resolve_zip_target_dir(self, plugin_root: Path) -> Path:
        """为本地插件包确定安装目录：已安装同 id 插件沿用原目录，否则进第三方目录"""
        pm = self._plugin_manager or get_plugin_manager()
        try:
            with open(plugin_root / self.PLUGIN_DESCRIPTOR_FILE, "r", encoding="utf-8") as f:
                descriptor_id = json.load(f).get("id", "")
        except (OSError, json.JSONDecodeError):
            descriptor_id = ""
        if descriptor_id:
            for scope, directory in (("official", pm.official_plugin_dir),
                                     ("thirdparty", pm.thirdparty_plugin_dir)):
                if pm.registry.find_by_descriptor(scope, descriptor_id):
                    return Path(directory)
        return Path(pm.thirdparty_plugin_dir)

    # ==================== GitHub Release 升级/降级 ====================

    def get_available_versions(self, source_url: str,
                               descriptor_path: str = "") -> List[ReleaseInfo]:
        """获取来源仓库的可安装版本列表（按插件版本号降序）

        对每个 Release tag 通过 Contents API 读取 IXPlugin.json 解析版本号，
        避免下载完整压缩包。

        Args:
            source_url: 来源仓库 URL
            descriptor_path: 描述文件在仓库中的路径（多插件仓库时为
                             {source_path}/IXPlugin.json，单插件仓库留空）

        Returns:
            ReleaseInfo 列表；解析失败/网络错误时返回空列表
        """
        parsed = self.parse_github_url(source_url)
        if not parsed:
            return []
        owner, repo = parsed

        releases = self._fetch_releases(owner, repo)
        if not releases:
            return []

        file_path = descriptor_path or self.PLUGIN_DESCRIPTOR_FILE
        results = []
        for rel in releases:
            tag = rel.get("tag_name", "")
            version = self._fetch_version_at_ref(owner, repo, tag, file_path)
            results.append(ReleaseInfo(
                tag=tag,
                name=rel.get("name") or tag,
                version=version or "",
                prerelease=bool(rel.get("prerelease", False)),
                published_at=rel.get("published_at", ""),
            ))
        results.sort(key=self._release_sort_key, reverse=True)
        return results

    def _fetch_releases(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        """查询仓库 Release 列表，失败返回空列表"""
        url = f"{self._gh_api_base}/repos/{owner}/{repo}/releases"
        try:
            response = requests.get(
                url, headers=self._github_headers(),
                params={"per_page": self.RELEASES_PER_PAGE},
                timeout=self.GITHUB_API_TIMEOUT
            )
            if response.status_code != 200:
                self._logger.warning(
                    get_name(), f"查询 Release 列表失败: HTTP {response.status_code}"
                )
                return []
            data = response.json()
            return data if isinstance(data, list) else []
        except Exception as e:
            self._logger.warning(get_name(), f"查询 Release 列表失败: {e}")
            return []

    def _fetch_version_at_ref(self, owner: str, repo: str, ref: str,
                              file_path: str) -> Optional[str]:
        """读取指定 ref 下描述文件的插件版本号"""
        desc = self._fetch_file_content(owner, repo, file_path, ref=ref)
        if not desc:
            return None
        return desc.get("version")

    def _release_sort_key(self, info: ReleaseInfo) -> tuple:
        """Release 排序键：可解析版本优先，按版本号降序"""
        try:
            v = PluginVersion.from_string(info.version)
            return (1, v.version_type.get_priority(), v.major, v.minor, v.patch)
        except ValueError:
            return (0, 0, 0, 0, 0)

    def install_release(
        self,
        owner: str,
        repo: str,
        tag: str,
        target_dir: Path,
        selected_plugins: List[str] = None,
        progress_callback=None
    ) -> List[InstallResult]:
        """安装指定 Release tag 对应的插件版本（升级或降级）

        Args:
            owner/repo/tag: GitHub 仓库与 Release tag
            target_dir: 安装目标目录
            selected_plugins: 多插件仓库时要安装的插件路径列表，None 安装全部
            progress_callback: 进度回调

        Returns:
            每个插件的安装结果列表
        """
        archive_url = f"https://github.com/{owner}/{repo}/archive/refs/tags/{tag}.zip"
        temp_dir, status = self._try_download_archive(archive_url, f"ix_plugin_{repo}_{tag}_")
        if temp_dir is None:
            return [InstallResult.error(f"下载 Release {tag} 失败 (HTTP {status})")]

        source_url = f"https://github.com/{owner}/{repo}"
        try:
            repo_index_path = temp_dir / self.REPO_INDEX_FILE
            if repo_index_path.exists():
                return self._install_from_multi_plugin_repo(
                    repo_index_path, target_dir, selected_plugins,
                    "GitHub Release", progress_callback, source_url=source_url
                )
            if not (temp_dir / self.PLUGIN_DESCRIPTOR_FILE).exists():
                return [InstallResult.error("该 Release 中未找到插件描述文件")]
            return self._install_single_plugin(
                temp_dir, target_dir, "GitHub Release", progress_callback,
                source_url=source_url
            )
        finally:
            self._cleanup_temp_dir(temp_dir)
