# 插件开发者 DataProvider 指南

本文档面向插件开发者，介绍如何在插件中使用 DataProvider 进行数据存储和跨插件通信。

---

## 1. 快速开始

### 1.1 在插件中初始化 DataProvider

```python
from core.plugin.plugin_interface import IPlugin
from core.data.data_provider import DataProvider

class MyPlugin(IPlugin):
    def __init__(self):
        self._cached_widget = None
        # 获取 DataProvider 单例
        self._data_provider = DataProvider()
        # 注册插件
        self._data_provider.register_plugin("my_plugin", "custom")

    @property
    def plugin_name(self) -> str:
        return "my_plugin"

    def _create_widget(self, parent=None, data_provider=None):
        widget = QWidget(parent)
        # ... 创建 UI
        return widget
```

---

## 2. 数据存储

### 2.1 保存数据

```python
# 保存配置（私有数据）
self._data_provider.set_plugin_data(
    instance_id="my_plugin",
    key="settings",
    value={"theme": "dark", "language": "zh-CN"},
    namespace="PRIVATE"
)

# 保存需要共享的数据
self._data_provider.set_plugin_data(
    instance_id="my_plugin",
    key="current_task",
    value={"title": "开发新功能", "progress": 50},
    namespace="PUBLIC"
)
```

### 2.2 读取数据

```python
# 读取私有配置
settings = self._data_provider.get_plugin_data(
    instance_id="my_plugin",
    key="settings",
    namespace="PRIVATE"
)

# 读取共享数据
current_task = self._data_provider.get_plugin_data(
    instance_id="my_plugin",
    key="current_task",
    namespace="PUBLIC"
)
```

---

## 3. 跨插件通信

### 3.1 发布数据变化

当你的插件数据发生变化时，通知其他插件：

```python
def update_tasks(self, new_tasks):
    # 更新数据
    self._data_provider.publish(
        publisher_id="task_manager",
        key="tasks",
        value=new_tasks,
        namespace="PUBLIC"
    )
```

### 3.2 订阅数据变化

监听其他插件的数据变化：

```python
def _create_widget(self, parent=None, data_provider=None):
    widget = QWidget(parent)
    layout = QVBoxLayout()

    # 创建任务列表显示
    self.task_label = QLabel("任务数: 0")
    layout.addWidget(self.task_label)

    # 订阅任务管理器的数据变化
    self._data_provider.subscribe(
        subscriber_id="my_plugin",
        target_plugin_id="task_manager",
        target_key="tasks",
        callback=self.on_tasks_changed,
        namespace="PUBLIC"
    )

    widget.setLayout(layout)
    return widget

def on_tasks_changed(self, old_value, new_value):
    # 更新 UI
    self.task_label.setText(f"任务数: {len(new_value)}")
    # 注意：UI 更新需要在主线程进行
```

---

## 4. 资源管理

### 4.1 保存文件

```python
# 保存图片
with open("icon.png", "rb") as f:
    image_data = f.read()

file_path = self._data_provider.save_asset(
    plugin_id="my_plugin",
    asset_name="icon.png",
    data=image_data
)
```

### 4.2 加载文件

```python
image_data = self._data_provider.load_asset(
    plugin_id="my_plugin",
    asset_name="icon.png"
)
```

---

## 5. 完整示例

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QLineEdit
from core.plugin.plugin_interface import IPlugin
from core.data.data_provider import DataProvider

class TaskManagerPlugin(IPlugin):
    def __init__(self):
        self._cached_widget = None
        self._data_provider = DataProvider()
        self._data_provider.register_plugin("task_manager", "official")

    @property
    def plugin_name(self) -> str:
        return "task_manager"

    def _create_widget(self, parent=None, data_provider=None):
        widget = QWidget(parent)
        layout = QVBoxLayout()

        # 标题
        title = QLabel("任务管理器")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # 任务输入
        self.task_input = QLineEdit()
        self.task_input.setPlaceholderText("输入新任务...")
        layout.addWidget(self.task_input)

        # 添加按钮
        add_btn = QPushButton("添加任务")
        add_btn.clicked.connect(self.add_task)
        layout.addWidget(add_btn)

        # 任务列表显示
        self.task_list_label = QLabel("暂无任务")
        layout.addWidget(self.task_list_label)

        # 加载已有任务
        self.refresh_task_list()

        # 订阅自身数据变化（可选，用于刷新UI）
        self._data_provider.subscribe(
            subscriber_id="task_manager",
            target_plugin_id="task_manager",
            target_key="tasks",
            callback=self.on_tasks_changed,
            namespace="PUBLIC"
        )

        widget.setLayout(layout)
        return widget

    def add_task(self):
        task_title = self.task_input.text().strip()
        if not task_title:
            return

        # 获取现有任务
        tasks = self._data_provider.get_plugin_data(
            "task_manager", "tasks", "PUBLIC"
        ) or []

        # 添加新任务
        tasks.append({"title": task_title, "done": False})

        # 发布更新
        self._data_provider.publish(
            publisher_id="task_manager",
            key="tasks",
            value=tasks,
            namespace="PUBLIC"
        )

        self.task_input.clear()

    def on_tasks_changed(self, old_value, new_value):
        self.refresh_task_list()

    def refresh_task_list(self):
        tasks = self._data_provider.get_plugin_data(
            "task_manager", "tasks", "PUBLIC"
        ) or []

        if not tasks:
            self.task_list_label.setText("暂无任务")
        else:
            task_text = "\n".join([
                f"[{'✓' if t.get('done') else ' '}] {t.get('title', '')}"
                for t in tasks
            ])
            self.task_list_label.setText(task_text)
```

---

## 6. 常见问题

### Q: 数据不生效？

检查：
1. 命名空间是否正确（PRIVATE vs PUBLIC）
2. instance_id 是否与插件名称一致

### Q: 订阅回调没有触发？

检查：
1. 是否使用了正确的 namespace
2. target_plugin_id 和 target_key 是否正确

### Q: 如何调试？

```python
# 添加日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 在关键位置添加日志
self._data_provider.set_plugin_data(...)
print(f"保存数据: {value}")
```

---

## 7. 快速参考

```python
# 初始化（插件 __init__ 中）
self._data_provider = DataProvider()
self._data_provider.register_plugin("my_plugin", "custom")

# 存数据
self._data_provider.set_plugin_data(instance_id, key, value, namespace)

# 取数据
self._data_provider.get_plugin_data(instance_id, key, namespace)

# 发布变化
self._data_provider.publish(publisher_id, key, value, namespace)

# 订阅变化
self._data_provider.subscribe(subscriber_id, target_plugin_id, target_key, callback, namespace)
```
