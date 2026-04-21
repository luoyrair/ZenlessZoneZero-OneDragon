import os
from pathlib import Path
from typing import List

import yaml

from one_dragon.base.screen.screen_info import ScreenInfo
from one_dragon.utils import yaml_utils


class ScreenConfigLoader:
    """画面配置加载器 - 支持内置和第三方插件"""

    def __init__(self, builtin_base_dir: str):
        """
        初始化加载器

        Args:
            builtin_base_dir: 内置 screen_info 根目录路径
        """
        self.builtin_base_dir = builtin_base_dir
        self.builtin_global_dir = os.path.join(builtin_base_dir, '_global')

        # 第三方插件画面目录列表 {app_id: plugin_screen_dir}
        self._third_party_apps: dict[str, str] = {}

    # ========== 第三方插件管理 ==========

    def add_third_party_plugins(self, plugin_dirs: list[tuple[Path, str]]) -> None:
        """
        批量添加第三方插件目录

        Args:
            plugin_dirs: application_plugin_dirs 返回的列表
        """
        from one_dragon.base.operation.application.plugin_info import PluginSource

        for plugin_dir, source in plugin_dirs:
            if source != PluginSource.THIRD_PARTY:
                continue

            # 第三方插件目录：plugins/ 是父目录，需要遍历其下的子目录
            if not plugin_dir.exists():
                continue

            # 遍历 plugins 目录下的每个插件子目录
            for sub_dir in plugin_dir.iterdir():
                if not sub_dir.is_dir():
                    continue

                # 检查插件是否有 screen 目录
                screen_dir = sub_dir / 'screen'
                if not screen_dir.exists():
                    continue

                # 扫描插件 screen 目录下的所有应用画面目录
                for item in screen_dir.iterdir():
                    if not item.is_dir():
                        continue
                    if item.name == '_global':
                        # 插件不能提供全局画面，跳过
                        continue

                    app_id = item.name
                    if app_id in self._third_party_apps:
                        # 同一个 app_id 被多个插件提供，报错
                        raise Exception(f"app_id '{app_id}' 已被插件 '{self._third_party_apps[app_id]}' 提供，当前插件 '{sub_dir}' 冲突")
                    self._third_party_apps[app_id] = str(sub_dir)

    def clear_third_party_plugins(self) -> None:
        """清空所有第三方插件"""
        self._third_party_apps.clear()

    def get_third_party_apps(self) -> dict[str, str]:
        """获取所有第三方插件应用 {app_id: plugin_dir}"""
        return self._third_party_apps.copy()

    # ========== 加载方法 ==========

    def load_global_screens(self) -> List[ScreenInfo]:
        """加载所有全局画面（仅内置）"""
        return self._load_screens_from_dir(self.builtin_global_dir, namespace='_global')

    def load_app_screens(self, app_id: str) -> List[ScreenInfo]:
        """
        加载指定应用的画面

        Args:
            app_id: 应用ID（全局唯一）
        """
        screens = []

        # 内置应用
        builtin_app_dir = os.path.join(self.builtin_base_dir, app_id)
        if os.path.exists(builtin_app_dir):
            screens.extend(self._load_screens_from_dir(builtin_app_dir, namespace=app_id))

        # 第三方插件应用
        if app_id in self._third_party_apps:
            plugin_dir = Path(self._third_party_apps[app_id])
            plugin_app_dir = plugin_dir / 'screen' / app_id
            if plugin_app_dir.exists():
                screens.extend(self._load_screens_from_dir(str(plugin_app_dir), namespace=app_id))

        return screens

    def load_all_app_screens(self) -> List[ScreenInfo]:
        """加载所有应用的画面（开发工具使用）"""
        all_screens = []

        all_screens.extend(self.load_global_screens())

        # 内置应用
        for item in os.listdir(self.builtin_base_dir):
            if item == '_global' or not os.path.isdir(os.path.join(self.builtin_base_dir, item)):
                continue
            all_screens.extend(self.load_app_screens(item))

        # 第三方插件应用
        for app_id in self._third_party_apps:
            builtin_app_dir = os.path.join(self.builtin_base_dir, app_id)
            if not os.path.exists(builtin_app_dir):
                all_screens.extend(self.load_app_screens(app_id))

        return all_screens

    @staticmethod
    def _load_screens_from_dir(directory: str, namespace: str) -> list[ScreenInfo]:
        """从目录加载所有 YAML 文件"""
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

            items = data if isinstance(data, list) else [data]
            for item in items:
                screen = ScreenInfo(item)
                original_name = item.get('screen_name', '')
                screen.set_namespace(namespace, original_name)
                screens.append(screen)

        return screens

    # ========== 保存方法 ==========

    def save_screen(self, screen: ScreenInfo, app_id: str | None = None) -> None:
        """
        保存画面到内置目录

        Args:
            screen: 要保存的画面信息
            app_id: 目标应用ID，None 表示全局
        """
        if app_id and app_id != '_global':
            target_dir = os.path.join(self.builtin_base_dir, app_id)
        else:
            target_dir = self.builtin_global_dir

        os.makedirs(target_dir, exist_ok=True)

        file_name = f"{screen.original_screen_name}.yml"
        file_path = os.path.join(target_dir, file_name)

        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(screen.to_dict(), f, allow_unicode=True,
                           default_flow_style=False, sort_keys=False)

    def delete_screen(self, screen: ScreenInfo, app_id: str | None = None) -> None:
        """删除内置目录中的画面文件"""
        if app_id and app_id != '_global':
            target_dir = os.path.join(self.builtin_base_dir, app_id)
        else:
            target_dir = self.builtin_global_dir

        file_name = f"{screen.original_screen_name}.yml"
        file_path = os.path.join(target_dir, file_name)

        if os.path.exists(file_path):
            os.remove(file_path)

    # ========== 辅助方法 ==========

    def get_app_dirs(self) -> List[str]:
        """获取所有应用目录名（不包括 _global）"""
        apps = set()

        # 内置应用
        for item in os.listdir(self.builtin_base_dir):
            if item == '_global' or not os.path.isdir(os.path.join(self.builtin_base_dir, item)):
                continue
            apps.add(item)

        # 第三方插件应用
        for app_id in self._third_party_apps:
            apps.add(app_id)

        return sorted(apps)

    def is_third_party_app(self, app_id: str) -> bool:
        """判断应用是否为第三方插件提供的"""
        return app_id in self._third_party_apps