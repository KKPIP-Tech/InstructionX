"""
GitHub 插件安装器

从 GitHub 仓库安装插件的核心逻辑，支持单插件和多插件仓库。
"""

import json
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from urllib.parse import urlparse

import requests

from utils.logging_tools import LoggerManager, get_name


@dataclass
class InstallResult:
    """插件安装结果"""
    success: bool
    message: str = ""
    plugin_id: Optional[str] = None
    plugin_name: Optional[str] = None

    @staticmethod
    def success(plugin_id: str, plugin_name: str, message: str = "安装成功") -> "InstallResult":
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
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict) and data.get("encoding") == "base64":
                    import base64
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
            response = requests.get(url, timeout=30)
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
        if not re.match(r"^(release|beta|alpha)\.\d+\.\d+\.\d+$", version):
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
        thirdparty_dir: Path = None
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
            from .manager import get_plugin_manager
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
                    repo_index_path, target_dir, selected_plugins, dir_desc
                )
            else:
                # 单插件仓库
                plugin_path = temp_dir / self.PLUGIN_DESCRIPTOR_FILE
                if not plugin_path.exists():
                    return [InstallResult.error("插件描述文件不存在")]

                return self._install_single_plugin(temp_dir, target_dir, dir_desc)
        finally:
            # 清理临时目录
            self._cleanup_temp_dir(temp_dir)

    def _download_repository(self, owner: str, repo: str) -> Optional[Path]:
        """下载整个仓库到临时目录"""
        temp_dir = None
        try:
            # 创建临时目录
            temp_dir = Path(tempfile.mkdtemp(prefix=f"ix_plugin_{repo}_"))

            # 使用 GitHub API 获取仓库信息
            archive_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/main.zip"
            try:
                response = requests.get(archive_url, timeout=60, stream=True)
                if response.status_code == 404:
                    # 尝试 master 分支
                    archive_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/master.zip"
                    response = requests.get(archive_url, timeout=60, stream=True)

                if response.status_code != 200:
                    self._logger.error(get_name(), f"Failed to download repo: {response.status_code}")
                    return None

                # 解压到临时目录
                import zipfile
                import io

                zip_content = io.BytesIO(response.content)
                with zipfile.ZipFile(zip_content) as zf:
                    # 获取顶层目录名（通常是 repo-main 或 repo-master）
                    all_names = zf.namelist()
                    if not all_names:
                        return None

                    # 找到根目录
                    root_prefix = all_names[0].split("/")[0] + "/"

                    # 解压所有文件，保持结构
                    for name in all_names:
                        if name.startswith(root_prefix):
                            target_name = name[len(root_prefix):]
                            if target_name:
                                target_path = temp_dir / target_name
                                if name.endswith("/"):
                                    target_path.mkdir(parents=True, exist_ok=True)
                                else:
                                    target_path.parent.mkdir(parents=True, exist_ok=True)
                                    with zf.open(name) as src, open(target_path, "wb") as dst:
                                        dst.write(src.read())

                return temp_dir

            except Exception as e:
                self._logger.error(get_name(), f"Error downloading repository: {e}")
                return None

        except Exception as e:
            self._logger.error(get_name(), f"Error creating temp directory: {e}")
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            return None

    def _install_from_multi_plugin_repo(
        self,
        repo_index_path: Path,
        target_dir: Path,
        selected_plugins: List[str],
        dir_desc: str
    ) -> List[InstallResult]:
        """从多插件仓库安装"""
        try:
            with open(repo_index_path, "r", encoding="utf-8") as f:
                repo_index = json.load(f)
        except Exception as e:
            return [InstallResult.error(f"读取仓库索引失败: {e}")]

        results = []
        plugins_list = repo_index.get("plugins", [])

        for plugin_entry in plugins_list:
            plugin_path_str = plugin_entry.get("path", "")
            plugin_id = plugin_entry.get("id", "")

            # 如果用户指定了插件，检查是否在列表中
            if selected_plugins is not None and plugin_path_str not in selected_plugins:
                continue

            plugin_dir = repo_index_path.parent / plugin_path_str
            if not plugin_dir.exists():
                results.append(InstallResult.error(f"插件目录不存在: {plugin_path_str}"))
                continue

            result = self._install_plugin_dir(plugin_dir, target_dir, plugin_id, dir_desc)
            results.append(result)

        return results

    def _install_single_plugin(
        self,
        plugin_root: Path,
        target_dir: Path,
        dir_desc: str
    ) -> List[InstallResult]:
        """安装单插件仓库（插件文件直接在仓库根目录）"""
        return self._install_plugin_dir(plugin_root, target_dir, "", dir_desc)

    def _install_plugin_dir(
        self,
        plugin_dir: Path,
        target_dir: Path,
        plugin_id: str = "",
        dir_desc: str = ""
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

            # 确定目标目录
            target_plugin_dir = target_dir / actual_plugin_id

            # 如果目标目录已存在，先移除（旧版本）
            if target_plugin_dir.exists():
                shutil.rmtree(target_plugin_dir, ignore_errors=True)

            # 创建目标目录
            target_dir.mkdir(parents=True, exist_ok=True)

            # 复制插件文件
            shutil.copytree(plugin_dir, target_plugin_dir)

            # 确保 __init__.py 存在
            init_file = target_plugin_dir / "__init__.py"
            if not init_file.exists():
                init_file.write_text("")

            self._logger.info(get_name(), f"插件已安装到 {target_plugin_dir}")
            return InstallResult.success(actual_plugin_id, plugin_name, f"安装成功 ({dir_desc})")

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
