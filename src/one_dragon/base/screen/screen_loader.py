import os

import yaml

from one_dragon.base.screen.screen_info import ScreenInfo
from one_dragon.utils import yaml_utils


class ScreenConfigLoader:
    """画面配置加载器 - 只负责从YAML加载和保存数据，不存储运行时状态"""

    def __init__(self, base_dir: str):
        """
        初始化加载器

        Args:
            base_dir: screen_info 根目录路径
        """
        self.base_dir = base_dir
        self.global_dir = os.path.join(base_dir, '_global')

    # ========== 加载方法 ==========

    def load_global_screens(self) -> list[ScreenInfo]:
        """加载所有全局画面"""
        return self._load_screens_from_dir(self.global_dir, namespace='_global')

    def load_app_screens(self, app_id: str) -> list[ScreenInfo]:
        """
        加载指定应用的画面

        Args:
            app_id: 应用ID（目录名）
        """
        app_dir = os.path.join(self.base_dir, app_id)
        if not os.path.exists(app_dir):
            return []
        return self._load_screens_from_dir(app_dir, namespace=app_id)

    def load_all_app_screens(self) -> list[ScreenInfo]:
        """加载所有应用的画面（开发工具使用）"""
        all_screens = []

        # 1. 加载全局
        all_screens.extend(self.load_global_screens())

        # 2. 遍历所有应用目录
        for item in os.listdir(self.base_dir):
            if item == '_global' or not os.path.isdir(os.path.join(self.base_dir, item)):
                continue
            all_screens.extend(self.load_app_screens(item))

        return all_screens

    def _load_screens_from_dir(self, directory: str, namespace: str) -> list[ScreenInfo]:
        """
        从目录加载所有 YAML 文件

        Args:
            directory: 目录路径
            namespace: 命名空间（_global 或 app_id）
        """
        screens = []
        if not os.path.exists(directory):
            return screens

        for file_name in os.listdir(directory):
            if not file_name.endswith('.yml'):
                continue

            file_path = os.path.join(directory, file_name)
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml_utils.safe_load(f)

            if not data:
                continue

            # 支持单文件多画面
            items = data if isinstance(data, list) else [data]
            for item in items:
                screen = ScreenInfo(item)
                if namespace != '_global':
                    screen.set_namespace(namespace, screen.screen_name)
                else:
                    screen.set_namespace('_global', screen.screen_name)
                screens.append(screen)

        return screens

    # ========== 保存方法 ==========

    def save_screen(self, screen: ScreenInfo, app_id: str | None = None) -> None:
        """
        保存画面到文件

        Args:
            screen: 要保存的画面信息
            app_id: 目标应用ID，None 表示全局
        """
        # 确定保存目录
        if app_id and app_id != '_global':
            target_dir = os.path.join(self.base_dir, app_id)
        else:
            target_dir = self.global_dir

        os.makedirs(target_dir, exist_ok=True)

        # 使用原始名称作为文件名
        file_name = f"{screen.screen_id}.yml"
        file_path = os.path.join(target_dir, file_name)

        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(screen.to_dict(), f, allow_unicode=True,
                           default_flow_style=False, sort_keys=False)

    def delete_screen(self, screen: ScreenInfo, app_id: str | None = None) -> None:
        """
        删除画面文件

        Args:
            screen: 要删除的画面信息
            app_id: 所属应用ID
        """
        if app_id and app_id != '_global':
            target_dir = os.path.join(self.base_dir, app_id)
        else:
            target_dir = self.global_dir

        file_name = f"{screen.screen_id}.yml"
        file_path = os.path.join(target_dir, file_name)

        if os.path.exists(file_path):
            os.remove(file_path)

    # ========== 辅助方法 ==========

    def get_app_dirs(self) -> list[str]:
        """获取所有应用目录名（不包括 _global）"""
        apps = []
        for item in os.listdir(self.base_dir):
            if item == '_global' or not os.path.isdir(os.path.join(self.base_dir, item)):
                continue
            apps.append(item)
        return apps