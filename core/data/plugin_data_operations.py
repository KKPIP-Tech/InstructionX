"""插件批量写入、分页读取与聚合查询，独立于兼容门面。"""

import copy
import sqlite3
from typing import Any, Dict

from core.interfaces.i_data_provider import DataNamespace

from .errors import DataProviderError
from .sqlite_backend import SQLiteBackend, SQLiteBackendError


class PluginDataOperations:
    """为 DataProvider 提供批量和大数据访问，保持单键 API 不变。"""

    def __init__(self, provider) -> None:
        self._provider = provider

    def set_batch(
        self,
        instance_id: str,
        values: Dict[str, Any],
        namespace: DataNamespace,
        notify: bool,
    ) -> None:
        """批量写入；公开数据按字典顺序通知，空字典为无操作。"""
        if not values:
            return
        if self._provider._use_json_backend:
            self._set_json_batch(instance_id, values, namespace, notify)
            return
        self._set_sqlite_batch(instance_id, values, namespace, notify)

    def _set_json_batch(self, instance_id, values, namespace, notify) -> None:
        provider = self._provider
        data = provider._json_load_data()
        self._require_json_plugin(data, instance_id)
        namespace_str = namespace.value
        old_values = self._json_values(data, instance_id, namespace_str)
        data["plugins"][instance_id][namespace_str].update(values)
        provider._cache = data
        provider._json_save_data()
        if namespace_str == DataNamespace.PUBLIC.value and notify:
            self._notify(instance_id, values, old_values)

    @staticmethod
    def _require_json_plugin(data: Dict, instance_id: str) -> None:
        if instance_id not in data["plugins"]:
            raise DataProviderError(f"插件 {instance_id} 不存在")

    @staticmethod
    def _json_values(data: Dict, instance_id: str, namespace: str) -> Dict[str, Any]:
        return dict(data["plugins"][instance_id][namespace])

    def _set_sqlite_batch(self, instance_id, values, namespace, notify) -> None:
        provider = self._provider
        namespace_str = namespace.value
        with provider._file_lock:
            try:
                self._require_sqlite_plugin(instance_id)
                old_values = self._sqlite_old_values(instance_id, namespace_str, notify)
                provider._backend.set_plugin_data_batch(instance_id, namespace_str, values)
            except (SQLiteBackendError, sqlite3.Error) as error:
                self._raise_backend(error)
            self._sync_full_cache(instance_id, namespace_str, values)
        if namespace_str == DataNamespace.PUBLIC.value and notify:
            self._notify(instance_id, values, old_values)

    def _require_sqlite_plugin(self, instance_id: str) -> None:
        if not self._provider._backend.plugin_exists(instance_id):
            raise DataProviderError(f"插件 {instance_id} 不存在")

    def _sqlite_old_values(self, instance_id: str, namespace: str, notify: bool) -> Dict:
        if namespace != DataNamespace.PUBLIC.value or not notify:
            return {}
        return self._provider._backend.get_all_plugin_data(instance_id, namespace)

    def _sync_full_cache(self, instance_id: str, namespace: str, values: Dict) -> None:
        cache = self._provider._cache
        if cache is None:
            return
        target = cache["plugins"][instance_id][namespace]
        for key, value in values.items():
            target[key] = copy.deepcopy(value)

    def _notify(self, instance_id: str, values: Dict, old_values: Dict) -> None:
        for key, value in values.items():
            self._provider._notify_subscribers(
                instance_id, key, old_values.get(key), copy.deepcopy(value)
            )

    def get_page(
        self,
        instance_id: str,
        namespace: DataNamespace,
        limit: int,
        offset: int,
    ) -> Dict[str, Any]:
        """分页读取插件数据，SQLite 使用 SQL 分页而非 Python 全量过滤。"""
        try:
            SQLiteBackend._validate_page(limit, offset)
        except SQLiteBackendError as error:
            self._raise_backend(error)
        if self._provider._use_json_backend:
            return self._json_page(instance_id, namespace, limit, offset)
        with self._provider._file_lock:
            try:
                self._require_sqlite_plugin(instance_id)
                return self._provider._backend.get_plugin_data_page(
                    instance_id, namespace.value, limit, offset
                )
            except (SQLiteBackendError, sqlite3.Error) as error:
                self._raise_backend(error)

    def _json_page(self, instance_id, namespace, limit, offset) -> Dict[str, Any]:
        data = self._provider._json_load_data()
        self._require_json_plugin(data, instance_id)
        values = self._json_values(data, instance_id, namespace.value)
        return dict(list(values.items())[offset:offset + limit])

    def count(self, instance_id: str, namespace: DataNamespace) -> int:
        """返回插件数据记录数，SQLite 使用 COUNT 聚合。"""
        if self._provider._use_json_backend:
            data = self._provider._json_load_data()
            self._require_json_plugin(data, instance_id)
            return len(self._json_values(data, instance_id, namespace.value))
        with self._provider._file_lock:
            try:
                self._require_sqlite_plugin(instance_id)
                return self._provider._backend.count_plugin_data(instance_id, namespace.value)
            except (SQLiteBackendError, sqlite3.Error) as error:
                self._raise_backend(error)

    @staticmethod
    def _raise_backend(error: SQLiteBackendError) -> None:
        raise DataProviderError(str(error)) from error
