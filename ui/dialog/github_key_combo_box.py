"""GitHub Key 选择框的弹层布局兼容实现。"""

from InstructionX_UIKit.components import ComboBox


class GitHubKeyComboBox(ComboBox):
    """修正 UIKit 弹层首次布局行距小于 QSS 项高的问题。"""

    def showPopup(self) -> None:
        """显示弹层后统一选项高度并重新布局，避免相邻选项重叠。"""
        super().showPopup()
        view = self.view()
        view.setUniformItemSizes(True)
        view.doItemsLayout()
