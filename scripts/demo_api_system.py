#!/usr/bin/env python3
"""
API 系统演示脚本
演示 PluginManager 的 API 调用功能
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.plugin.manager import PluginManager


def print_header(title: str):
    """打印标题"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def print_subheader(title: str):
    """打印子标题"""
    print("\n" + "-" * 70)
    print(f"  {title}")
    print("-" * 70)


def demo_api_discovery(manager: PluginManager):
    """演示 API 发现功能"""
    print_header("1. API 发现功能")
    
    # 获取所有插件的 API
    all_apis = manager.get_all_apis()
    
    if not all_apis:
        print("❌ 没有找到任何已注册的 API")
        return
    
    print(f"✓ 找到 {len(all_apis)} 个插件提供了 API:\n")
    
    for plugin_id, api_info in all_apis.items():
        print(f"📦 插件名称: {api_info['plugin_name']}")
        print(f"   插件 ID: {plugin_id}")
        print(f"   插件类型: {api_info['plugin_type']}")
        print(f"   可用方法: {', '.join(api_info['methods'])}")
        print(f"   方法数量: {len(api_info['methods'])}")
        print()


def demo_api_details(manager: PluginManager):
    """演示获取 API 详细信息"""
    print_header("2. API 详细信息")
    
    # 获取字符串工具插件的 ID
    string_tools_id = manager.get_plugin_id_by_name("字符串\n工具")
    
    if not string_tools_id:
        print("❌ 未找到字符串工具插件")
        return
    
    print(f"✓ 找到字符串工具插件: {string_tools_id}\n")
    
    # 获取插件的 API 信息
    plugin_api = manager.get_plugin_api(string_tools_id)
    
    if not plugin_api:
        print("❌ 该插件未注册 API")
        return
    
    print(f"插件名称: {plugin_api['plugin_name']}")
    print(f"插件类型: {plugin_api['plugin_type']}")
    print(f"方法数量: {len(plugin_api['methods'])}\n")
    
    # 显示所有方法的详细信息
    print_subheader("方法详细信息")
    
    for method_name in plugin_api['methods']:
        method_desc = manager.get_api_description(string_tools_id, method_name)
        print(f"\n方法名: {method_name}")
        print(f"描述: {method_desc.get('description', 'N/A')}")
        
        # 显示参数
        params = method_desc.get('parameters', {})
        if params:
            print("参数:")
            for param_name, param_info in params.items():
                required = "必需" if param_info.get('required', False) else "可选"
                print(f"  - {param_name} ({param_info.get('type', 'any')})")
                print(f"    描述: {param_info.get('description', 'N/A')}")
                print(f"    是否必需: {required}")
                
                if 'default' in param_info:
                    print(f"    默认值: {param_info['default']}")
        
        # 显示返回值
        returns = method_desc.get('returns', {})
        if returns:
            print(f"返回值: {returns.get('type', 'any')}")
            print(f"  描述: {returns.get('description', 'N/A')}")


def demo_api_call(manager: PluginManager):
    """演示 API 调用"""
    print_header("3. API 调用演示")
    
    # 获取字符串工具插件的 ID
    string_tools_id = manager.get_plugin_id_by_name("字符串\n工具")
    
    if not string_tools_id:
        print("❌ 未找到字符串工具插件")
        return
    
    print(f"✓ 目标插件: {string_tools_id}")
    
    # 测试文本
    test_texts = [
        "Hello World",
        "Python is Awesome!",
        "  Extra  Spaces  ",
        "this is a test sentence"
    ]
    
    methods_to_test = [
        ("to_uppercase", "转换为大写"),
        ("to_lowercase", "转换为小写"),
        ("reverse_text", "反转文本"),
        ("capitalize_words", "单词首字母大写"),
        ("remove_whitespace", "移除空白字符"),
        ("count_words", "统计单词数"),
        ("count_chars", "统计字符数（不含空格）")
    ]
    
    for text in test_texts:
        print_subheader(f"测试文本: \"{text}\"")
        
        for method_name, description in methods_to_test:
            try:
                if method_name == "count_chars":
                    # 特殊处理：需要额外参数
                    result = manager.call_plugin_method(
                        caller_id="demo-script",
                        plugin_id=string_tools_id,
                        method_name=method_name,
                        text=text,
                        include_spaces=False
                    )
                else:
                    result = manager.call_plugin_method(
                        caller_id="demo-script",
                        plugin_id=string_tools_id,
                        method_name=method_name,
                        text=text
                    )
                
                print(f"  ✓ {description:20s} -> {result}")
                
            except Exception as e:
                print(f"  ✗ {description:20s} -> 错误: {str(e)}")


def demo_error_handling(manager: PluginManager):
    """演示错误处理"""
    print_header("4. 错误处理演示")
    
    print_subheader("1. 调用不存在的插件")
    
    try:
        result = manager.call_plugin_method(
            caller_id="demo-script",
            plugin_id="non-existent-plugin",
            method_name="to_uppercase",
            text="test"
        )
        print(f"  结果: {result}")
    except ValueError as e:
        print(f"  ✓ 捕获到 ValueError: {str(e)}")
    except Exception as e:
        print(f"  ✗ 未捕获的异常: {type(e).__name__}: {str(e)}")
    
    print_subheader("2. 调用不存在的方法")
    
    string_tools_id = manager.get_plugin_id_by_name("字符串\n工具")
    if string_tools_id:
        try:
            result = manager.call_plugin_method(
                caller_id="demo-script",
                plugin_id=string_tools_id,
                method_name="non_existent_method",
                text="test"
            )
            print(f"  结果: {result}")
        except ValueError as e:
            print(f"  ✓ 捕获到 ValueError: {str(e)}")
        except Exception as e:
            print(f"  ✗ 未捕获的异常: {type(e).__name__}: {str(e)}")
    
    print_subheader("3. 传递错误的参数")
    
    if string_tools_id:
        try:
            result = manager.call_plugin_method(
                caller_id="demo-script",
                plugin_id=string_tools_id,
                method_name="to_uppercase",
                # 故意不传递 text 参数
            )
            print(f"  结果: {result}")
        except (ValueError, RuntimeError, TypeError) as e:
            print(f"  ✓ 捕获到异常: {type(e).__name__}: {str(e)}")
        except Exception as e:
            print(f"  ✗ 未捕获的异常: {type(e).__name__}: {str(e)}")


def demo_function_tools(manager: PluginManager):
    """演示 Function Tools 生成"""
    print_header("5. Function Tools 生成演示")
    
    # 获取所有 function tools
    tools = manager.get_all_function_tools()
    
    if not tools:
        print("❌ 没有可用的 Function Tools")
        return
    
    print(f"✓ 生成了 {len(tools)} 个 Function Tools\n")
    
    # 显示前 3 个 tools 的详细信息
    print_subheader("Function Tools 示例（前 3 个）")
    
    for i, tool in enumerate(tools[:3], 1):
        function_info = tool['function']
        print(f"\n#{i}. {function_info['name']}")
        print(f"   描述: {function_info['description']}")
        
        # 显示参数
        params = function_info['parameters']
        if params.get('properties'):
            print("   参数:")
            for param_name, param_info in params['properties'].items():
                print(f"     - {param_name} ({param_info['type']}): {param_info['description']}")
        
        # 显示必需参数
        if params.get('required'):
            print(f"   必需参数: {', '.join(params['required'])}")
    
    print(f"\n... 还有 {len(tools) - 3} 个 tools")
    print("\n💡 这些 Function Tools 可以直接用于 OpenAI Function Calling 或 MCP 服务器")


def main():
    """主函数"""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 15 + "API 系统演示程序" + " " * 28 + "║")
    print("╚" + "=" * 68 + "╝")
    
    print("\n本程序演示 PluginManager 的 API 调用功能：")
    print("  1. API 发现")
    print("  2. API 详细信息查询")
    print("  3. API 调用")
    print("  4. 错误处理")
    print("  5. Function Tools 生成")
    
    # 初始化 PluginManager
    print_subheader("加载插件")
    
    manager = PluginManager()
    manager.load_plugins()
    
    # 显示已加载的插件
    all_plugins = manager.get_all_plugins()
    print(f"✓ 已加载 {len(all_plugins)} 个插件")
    
    for plugin in all_plugins:
        print(f"  - {plugin.plugin_name} (ID: {plugin.plugin_id})")
    
    # 运行演示
    try:
        demo_api_discovery(manager)
        demo_api_details(manager)
        demo_api_call(manager)
        demo_error_handling(manager)
        demo_function_tools(manager)
        
        print_header("演示完成！")
        print("✅ 所有演示已完成")
        print("\n💡 提示:")
        print("  - 查看完整文档: docs/API_DEMO_GUIDE.md")
        print("  - 查看 API 指南: docs/PLUGIN_API_GUIDE.md")
        print("  - 查看 API 调用示例: docs/API_CALLING_GUIDE.md")
        
    except KeyboardInterrupt:
        print("\n\n⚠ 演示被用户中断")
    except Exception as e:
        print(f"\n\n❌ 演示过程中发生错误:")
        print(f"   错误类型: {type(e).__name__}")
        print(f"   错误信息: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print("\n")


if __name__ == "__main__":
    main()