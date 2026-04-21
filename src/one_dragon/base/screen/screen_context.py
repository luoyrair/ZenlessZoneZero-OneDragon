# one_dragon/base/screen/screen_context.py
import os
from pathlib import Path
from typing import Optional

from one_dragon.base.screen.screen_area import ScreenArea
from one_dragon.base.screen.screen_info import ScreenInfo
from one_dragon.base.screen.screen_loader import ScreenConfigLoader
from one_dragon.utils import os_utils
from one_dragon.utils.log_utils import log


class ScreenRouteNode:
    """记录一个画面跳转的节点"""

    def __init__(self, from_screen: str, from_area: str, to_screen: str):
        self.from_screen: str = from_screen
        self.from_area: str = from_area
        self.to_screen: str = to_screen


class ScreenRoute:
    """记录两个画面之间的跳转路径"""

    def __init__(self, from_screen: str, to_screen: str):
        self.from_screen: str = from_screen
        self.to_screen: str = to_screen
        self.node_list: list[ScreenRouteNode] = []

    @property
    def can_go(self) -> bool:
        return len(self.node_list) > 0


class ScreenContext:
    """
    画面运行时上下文

    职责：
    - 存储运行时需要的画面配置（当前应用 + 全局）
    - 管理当前画面状态
    - 计算和缓存跳转路径
    - 提供画面/区域查询接口

    不负责：
    - 配置文件的加载/保存（由 ScreenConfigLoader 负责）
    """

    def __init__(self):
        # 配置加载器（延迟初始化）
        self._loader: ScreenConfigLoader | None = None

        # 运行时数据存储
        self.screen_info_list: list[ScreenInfo] = []
        self.screen_info_map: dict[str, ScreenInfo] = {}
        self._screen_area_map: dict[str, ScreenArea] = {}
        self._id_2_screen: dict[str, ScreenInfo] = {}

        # 路径图（分离存储）
        self._global_route_map: dict[str, dict[str, ScreenRoute]] = {}
        self._app_route_maps: dict[str, dict[str, dict[str, ScreenRoute]]] = {}

        # 运行时状态
        self.last_screen_name: Optional[str] = None
        self.current_screen_name: Optional[str] = None

        # 当前加载的应用ID
        self._current_app_id: str | None = None

    @property
    def yml_file_dir(self) -> str:
        """获取 screen_info 目录路径"""
        return os_utils.get_path_under_work_dir('assets', 'game_data', 'screen_info')

    @property
    def global_screen_dir(self) -> str:
        """获取全局画面目录"""
        return os.path.join(self.yml_file_dir, '_global')

    @property
    def loader(self) -> ScreenConfigLoader:
        """获取配置加载器（延迟初始化）"""
        if self._loader is None:
            self._loader = ScreenConfigLoader(self.yml_file_dir)
        return self._loader

    @property
    def current_app_id(self) -> str | None:
        """获取当前加载的应用ID"""
        return self._current_app_id

    # ========== 第三方插件管理 ==========

    def add_third_party_plugins(self, plugin_dirs: list[tuple[Path, str]]) -> None:
        """
        批量添加第三方插件目录

        Args:
            plugin_dirs: application_plugin_dirs 返回的列表
        """
        self.loader.add_third_party_plugins(plugin_dirs)
        # 如果当前有加载的应用，需要重新加载
        if self._current_app_id is not None:
            self.reload(from_memory=False, app_id=self._current_app_id)

    def clear_third_party_plugins(self) -> None:
        """清空所有第三方插件"""
        self.loader.clear_third_party_plugins()
        if self._current_app_id is not None:
            self.reload(from_memory=False, app_id=self._current_app_id)

    # ========== 配置加载 ==========

    def reload(self, from_memory: bool = False, app_id: str | None = None) -> None:
        """
        重新加载配置文件

        Args:
            from_memory: 是否从内存中加载（保存后刷新使用）
            app_id: 指定应用ID，为 None 时只加载 _global
        """
        self.screen_info_list.clear()
        self.screen_info_map.clear()
        self._screen_area_map.clear()

        if from_memory:
            self._load_from_memory()
        else:
            self._load_from_files(app_id)

        if app_id is None:
            log.info(f"加载了 {len(self.screen_info_list)} 个画面，{len(self._screen_area_map)} 个区域")

        self._init_screen_route()

    def _load_from_memory(self) -> None:
        """从内存中的 _id_2_screen 加载（保存后刷新）"""
        for screen_info in self._id_2_screen.values():
            self._add_screen(screen_info)

    def _load_from_files(self, app_id: str | None = None) -> None:
        """从文件系统加载画面配置"""
        # 清空内存存储
        self._id_2_screen.clear()

        # 1. 加载全局画面
        global_screens = self.loader.load_global_screens()
        for screen in global_screens:
            self._add_screen(screen)
            self._id_2_screen[screen.screen_id] = screen

        # 2. 加载应用专属画面
        if app_id is not None:
            app_screens = self.loader.load_app_screens(app_id)
            for screen in app_screens:
                self._add_screen(screen)
                self._id_2_screen[screen.screen_id] = screen

        self._current_app_id = app_id

    def _add_screen(self, screen: ScreenInfo) -> None:
        """添加画面到内部存储"""
        self.screen_info_list.append(screen)
        self.screen_info_map[screen.screen_name] = screen
        for area in screen.area_list:
            self._screen_area_map[f'{screen.screen_name}.{area.area_name}'] = area

    # ========== 画面/区域查询 ==========

    def get_screen(self, screen_name: str, copy: bool = False, app_id: str | None = None) -> ScreenInfo:
        """
        获取某个画面

        Args:
            screen_name: 画面名称（支持带命名空间或不带）
            copy: 是否返回副本
            app_id: 指定应用ID（用于命名空间补全）
        """
        # 构建查找列表
        to_try = [screen_name]

        # 如果提供了 app_id，尝试加前缀
        if app_id and app_id != '_global':
            to_try.append(f"{app_id}.{screen_name}")

        # 如果有当前 app_id 且与传入的不同，也尝试
        if self._current_app_id and self._current_app_id != '_global' and self._current_app_id != app_id:
            to_try.append(f"{self._current_app_id}.{screen_name}")

        # 尝试查找
        for key in to_try:
            screen = self.screen_info_map.get(key)
            if screen is not None:
                if copy:
                    return ScreenInfo(screen.to_dict())
                return screen

        raise Exception(f"未找到画面: {screen_name}")

    def get_area(self, screen_name: str, area_name: str, app_id: str | None = None) -> ScreenArea | None:
        """
        获取某个区域的信息

        Args:
            screen_name: 画面名称
            area_name: 区域名称
            app_id: 指定应用ID（用于命名空间补全）
        """
        to_try = [f'{screen_name}.{area_name}']

        if app_id and app_id != '_global':
            to_try.append(f"{app_id}.{screen_name}.{area_name}")

        if self._current_app_id and self._current_app_id != '_global' and self._current_app_id != app_id:
            to_try.append(f"{self._current_app_id}.{screen_name}.{area_name}")

        for key in to_try:
            area = self._screen_area_map.get(key)
            if area is not None:
                return area

        return None

    # ========== 路径计算 ==========

    def _init_screen_route(self) -> None:
        """初始化画面间的跳转路径（分离计算）"""
        # 1. 收集全局画面
        global_screens = []
        app_screens_map: dict[str, list[ScreenInfo]] = {}

        for screen in self.screen_info_list:
            namespace = getattr(screen, '_namespace', None)
            if namespace == '_global' or namespace is None:
                global_screens.append(screen)
            elif namespace != '_legacy':
                if namespace not in app_screens_map:
                    app_screens_map[namespace] = []
                app_screens_map[namespace].append(screen)

        # 2. 计算全局路径图
        if global_screens:
            self._global_route_map = self._compute_routes(global_screens, app_id='_global')
        else:
            self._global_route_map = {}

        # 3. 计算各应用路径图
        self._app_route_maps.clear()
        for app_id, app_screens in app_screens_map.items():
            all_screens = app_screens + global_screens
            self._app_route_maps[app_id] = self._compute_routes(all_screens, app_id=app_id)

    def _compute_routes(self, screens: list[ScreenInfo], app_id: str = None) -> dict[str, dict[str, ScreenRoute]]:
        """计算给定画面列表的路径图（Floyd-Warshall）"""
        screen_map = {s.screen_name: s for s in screens}

        # 初始化 route_map
        route_map: dict[str, dict[str, ScreenRoute]] = {}
        for screen_1 in screens:
            route_map[screen_1.screen_name] = {}
            for screen_2 in screens:
                route_map[screen_1.screen_name][screen_2.screen_name] = ScreenRoute(
                    from_screen=screen_1.screen_name,
                    to_screen=screen_2.screen_name
                )

        # 根据 goto_list 初始化边
        for screen_info in screens:
            for area in screen_info.area_list:
                if not area.goto_list:
                    continue

                from_screen_route = route_map.get(screen_info.screen_name)
                if from_screen_route is None:
                    log.error('画面路径没有初始化 %s', screen_info.screen_name)
                    continue

                for goto_screen_name in area.goto_list:
                    matched = self._find_target_screen(
                        goto_screen_name,
                        screen_map,
                        app_id=app_id,
                        from_screen=screen_info.screen_name
                    )

                    if matched is None:
                        if app_id != '_global':
                            log.warning(f'画面路径 {screen_info.screen_name} -> {goto_screen_name} 无法找到目标画面')
                        continue

                    from_screen_route[matched].node_list.append(
                        ScreenRouteNode(
                            from_screen=screen_info.screen_name,
                            from_area=area.area_name,
                            to_screen=matched
                        )
                    )

        # Floyd-Warshall 计算最短路径
        screen_list = list(screen_map.keys())
        screen_len = len(screen_list)

        for k in range(screen_len):
            screen_k = screen_list[k]
            for i in range(screen_len):
                if i == k:
                    continue
                screen_i = screen_list[i]

                route_ik = route_map[screen_i][screen_k]
                if not route_ik.can_go:
                    continue

                for j in range(screen_len):
                    if k == j or i == j:
                        continue
                    screen_j = screen_list[j]

                    route_kj = route_map[screen_k][screen_j]
                    if not route_kj.can_go:
                        continue

                    route_ij = route_map[screen_i][screen_j]

                    if (not route_ij.can_go
                            or len(route_ik.node_list) + len(route_kj.node_list) < len(route_ij.node_list)):
                        route_ij.node_list = route_ik.node_list + route_kj.node_list

        return route_map

    def _find_target_screen(self, target: str, screen_map: dict, app_id: str = None,
                            from_screen: str = None) -> str | None:
        """查找目标画面（支持命名空间自动补全）"""
        # 1. 直接匹配
        if target in screen_map:
            return target

        # 2. 从源画面提取命名空间尝试
        if from_screen and '.' in from_screen:
            from_namespace = from_screen.split('.')[0]
            namespaced = f"{from_namespace}.{target}"
            if namespaced in screen_map:
                return namespaced

        # 3. 用当前应用 ID 尝试
        if app_id and app_id != '_global':
            namespaced = f"{app_id}.{target}"
            if namespaced in screen_map:
                return namespaced

        # 4. 用当前加载的应用 ID 尝试
        if self._current_app_id and self._current_app_id != '_global' and self._current_app_id != app_id:
            namespaced = f"{self._current_app_id}.{target}"
            if namespaced in screen_map:
                return namespaced

        # 5. 在所有画面中查找以 .{target} 结尾的
        for name in screen_map.keys():
            if name.endswith(f".{target}"):
                return name

        return None

    def get_screen_route(self, from_screen: str, to_screen: str, app_id: str | None = None) -> Optional[ScreenRoute]:
        """获取两个画面之间的跳转路径"""
        target_app = app_id or self._current_app_id

        # 优先使用应用路径图
        if target_app and target_app in self._app_route_maps:
            route_map = self._app_route_maps[target_app]

            from_matched = self._match_screen_in_route(from_screen, route_map, target_app)
            to_matched = self._match_screen_in_route(to_screen, route_map, target_app)

            if from_matched and to_matched:
                route = route_map.get(from_matched, {}).get(to_matched)
                if route and route.can_go:
                    return route

        # 降级使用全局路径图
        from_matched = self._match_screen_in_route(from_screen, self._global_route_map, '_global')
        to_matched = self._match_screen_in_route(to_screen, self._global_route_map, '_global')

        if from_matched and to_matched:
            route = self._global_route_map.get(from_matched, {}).get(to_matched)
            if route and route.can_go:
                return route

        return None

    def _match_screen_in_route(self, screen_name: str, route_map: dict, app_id: str) -> str | None:
        """在路径图中匹配画面名称"""
        if screen_name in route_map:
            return screen_name

        if app_id != '_global':
            namespaced = f"{app_id}.{screen_name}"
            if namespaced in route_map:
                return namespaced

        for name in route_map.keys():
            if name.endswith(f".{screen_name}"):
                return name

        return None

    # ========== 运行时状态管理 ==========

    def update_current_screen_name(self, screen_name: str) -> None:
        """更新当前的画面名字"""
        self.last_screen_name = self.current_screen_name
        self.current_screen_name = screen_name

    def switch_app(self, app_id: str) -> None:
        """切换当前应用，重新加载画面配置"""
        if app_id == self._current_app_id:
            log.debug(f"已在应用 {app_id} 的上下文中，无需切换")
            return
        log.info(f"切换画面上下文: {self._current_app_id} -> {app_id}")
        self.reload(from_memory=False, app_id=app_id)
        log.info(f"加载了 {len(self.screen_info_list)} 个画面，{len(self._screen_area_map)} 个区域")

    # ========== 保存/删除（委托给 Loader） ==========

    def save_screen(self, screen_info: ScreenInfo, app_id: str | None = None) -> None:
        """
        保存画面到内置目录

        Args:
            screen_info: 要保存的画面信息
            app_id: 目标应用ID，None 表示从命名空间推断
        """
        # 确定目标应用ID
        target_app_id = app_id
        if target_app_id is None:
            if '.' in screen_info.screen_name:
                target_app_id = screen_info.screen_name.split('.')[0]
            else:
                target_app_id = '_global'

        # 保存到文件（只保存到内置目录，不保存到第三方插件）
        save_app_id = target_app_id if target_app_id != '_global' else None
        self.loader.save_screen(screen_info, app_id=save_app_id)

        # 更新内存中的存储
        self._id_2_screen[screen_info.screen_id] = screen_info
        screen_info._loaded_app_id = target_app_id

        # 重新加载到运行时
        self.reload(from_memory=True, app_id=self._current_app_id)

    def delete_screen(self, screen_id: str, app_id: str | None = None) -> None:
        """
        删除一个画面（只删除内置目录中的画面）

        Args:
            screen_id: 画面ID
            app_id: 所属应用ID
        """
        if screen_id not in self._id_2_screen:
            return

        screen_info = self._id_2_screen[screen_id]
        actual_app_id = app_id or getattr(screen_info, '_loaded_app_id', None)

        # 从文件删除（只删除内置目录）
        delete_app_id = actual_app_id if actual_app_id != '_global' else None
        self.loader.delete_screen(screen_info, app_id=delete_app_id)

        # 从内存删除
        del self._id_2_screen[screen_id]

        # 重新加载到运行时
        self.reload(from_memory=True, app_id=self._current_app_id)

    def is_third_party_app(self, app_id: str) -> bool:
        """判断应用是否为第三方插件提供的"""
        return self.loader.is_third_party_app(app_id)