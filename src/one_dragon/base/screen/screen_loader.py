import os
from typing import Optional

import yaml

from one_dragon.base.screen.screen_area import ScreenArea
from one_dragon.base.screen.screen_info import ScreenInfo
from one_dragon.utils import os_utils, yaml_utils
from one_dragon.utils.log_utils import log


class ScreenRouteNode:

    def __init__(self, from_screen: str, from_area: str, to_screen: str):
        """
        记录一个画面跳转的节点
        :param from_screen: 从某个画面出发
        :param from_area: 点击某个区域
        :param to_screen: 可以前往某个目标画面
        """
        self.from_screen: str = from_screen
        self.from_area: str = from_area
        self.to_screen: str = to_screen


class ScreenRoute:

    def __init__(self, from_screen: str, to_screen: str):
        """
        记录两个画面质检跳转的路径
        :param from_screen:
        :param to_screen:
        """
        self.from_screen: str = from_screen
        self.to_screen: str = to_screen
        self.node_list: list[ScreenRouteNode] = []

    @property
    def can_go(self) -> bool:
        """
        :return: 可到达
        """
        return self.node_list is not None and len(self.node_list) > 0


class ScreenContext:

    def __init__(self):
        # 当前加载的应用ID
        self._current_app_id: str | None = None

        # 画面数据存储（带命名空间）
        self.screen_info_list: list[ScreenInfo] = []
        self.screen_info_map: dict[str, ScreenInfo] = {}
        self._screen_area_map: dict[str, ScreenArea] = {}
        self._id_2_screen: dict[str, ScreenInfo] = {}

        # 路径图（分离存储）
        self._global_route_map: dict[str, dict[str, ScreenRoute]] = {}
        self._app_route_maps: dict[str, dict[str, dict[str, ScreenRoute]]] = {}

        # 当前画面状态
        self.last_screen_name: Optional[str] = None
        self.current_screen_name: Optional[str] = None

    @property
    def yml_file_dir(self) -> str:
        return os_utils.get_path_under_work_dir('assets', 'game_data', 'screen_info')

    @property
    def global_screen_dir(self) -> str:
        """全局画面目录"""
        return os.path.join(self.yml_file_dir, '_global')

    def get_app_screen_dir(self, app_id: str) -> str:
        """获取应用专属画面目录"""
        return os.path.join(self.yml_file_dir, app_id)

    def _get_screen_dir(self, app_id: str | None = None) -> str:
        """根据 app_id 获取画面文件存放目录"""
        if app_id is None or app_id == '_global':
            return self.global_screen_dir
        else:
            return self.get_app_screen_dir(app_id)

    @property
    def merge_yml_file_path(self) -> str:
        return os.path.join(self.yml_file_dir, '_od_merged.yml')

    def get_yml_file_path(self, screen_id: str, app_id: str | None = None) -> str:
        """获取画面文件路径"""
        screen_dir = self._get_screen_dir(app_id)
        return os.path.join(screen_dir, f'{screen_id}.yml')

    @property
    def current_app_id(self) -> str | None:
        return self._current_app_id

    def reload(self, from_memory: bool = False, from_separated_files: bool = False, app_id: str | None = None) -> None:
        """
        重新加载配置文件

        Args:
            from_memory: 是否从内存中加载
            from_separated_files: 是否从新目录结构加载
            app_id: 指定应用ID，为 None 时只加载 _global
        """
        self.screen_info_list.clear()
        self.screen_info_map.clear()
        self._screen_area_map.clear()

        if from_memory:
            for screen_info in self._id_2_screen.values():
                self.screen_info_list.append(screen_info)
                self.screen_info_map[screen_info.screen_name] = screen_info
                for screen_area in screen_info.area_list:
                    self._screen_area_map[f'{screen_info.screen_name}.{screen_area.area_name}'] = screen_area
        elif from_separated_files:
            self._current_app_id = app_id
            self._load_for_app(app_id)
        else:
            self._load_from_legacy_merged_file()

        if app_id is None:
            log.info(f"加载了 {len(self.screen_info_list)} 个画面，{len(self._screen_area_map)} 个区域")
        self.init_screen_route()

    def _load_for_app(self, app_id: str | None = None) -> None:
        """按应用加载画面配置"""
        self._id_2_screen.clear()

        # 1. 始终加载全局画面
        if os.path.exists(self.global_screen_dir):
            self._load_screens_from_dir(self.global_screen_dir, app_id='_global')

        # 2. 加载指定应用的专属画面
        if app_id is not None:
            app_dir = self.get_app_screen_dir(app_id)
            if os.path.exists(app_dir):
                self._load_screens_from_dir(app_dir, app_id=app_id)

    def _load_screens_from_dir(self, directory: str, app_id: str) -> None:
        """从指定目录加载所有 yml 文件"""
        if not os.path.exists(directory):
            return

        for file_name in os.listdir(directory):
            if not file_name.endswith('.yml'):
                continue
            file_path = os.path.join(directory, file_name)
            with open(file_path, 'r', encoding='utf-8') as file:
                log.debug(f"加载yaml: {file_path}")
                data = yaml_utils.safe_load(file)

            if not isinstance(data, dict):
                log.warning(f"画面配置格式错误，已跳过: {file_path}")
                continue

            screen_info = ScreenInfo(data)

            # 设置命名空间
            original_name = data.get('screen_name', '')
            if app_id != '_global':
                screen_info.set_namespace(app_id, original_name)
            else:
                screen_info.set_namespace('_global', original_name)

            screen_info._loaded_app_id = app_id

            self.screen_info_list.append(screen_info)
            self.screen_info_map[screen_info.screen_name] = screen_info
            self._id_2_screen[screen_info.screen_id] = screen_info

            for screen_area in screen_info.area_list:
                self._screen_area_map[f'{screen_info.screen_name}.{screen_area.area_name}'] = screen_area

    def _load_from_legacy_merged_file(self) -> None:
        """从旧的合并文件加载（兼容旧版）"""
        self._id_2_screen.clear()
        file_path = self.merge_yml_file_path
        if not os.path.exists(file_path):
            log.warning(f"合并配置文件不存在: {file_path}")
            return

        with open(file_path, 'r', encoding='utf-8') as file:
            log.debug(f"加载yaml: {file_path}")
            yaml_data = yaml_utils.safe_load(file)

        if not isinstance(yaml_data, list):
            if yaml_data is not None:
                log.warning(f"合并画面配置格式错误，已忽略: {file_path}")
            yaml_data = []

        for data in yaml_data:
            if not isinstance(data, dict):
                log.warning(f"合并画面配置中存在非字典条目，已跳过: {file_path}")
                continue
            screen_info = ScreenInfo(data)
            screen_info._namespace = '_legacy'
            self.screen_info_list.append(screen_info)
            self.screen_info_map[screen_info.screen_name] = screen_info
            self._id_2_screen[screen_info.screen_id] = screen_info
            for screen_area in screen_info.area_list:
                self._screen_area_map[f'{screen_info.screen_name}.{screen_area.area_name}'] = screen_area

    def get_screen(self, screen_name: str, copy: bool = False, app_id: str | None = None) -> ScreenInfo:
        """获取某个画面"""
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
            screen = self.screen_info_map.get(key, None)
            if screen is not None:
                if copy:
                    return ScreenInfo(screen.to_dict())
                return screen

        raise Exception(f"未找到画面: {screen_name}")

    def get_area(self, screen_name: str, area_name: str, app_id: str | None = None) -> ScreenArea:
        """获取某个区域的信息"""
        to_try = [f'{screen_name}.{area_name}']

        if app_id and app_id != '_global':
            to_try.append(f"{app_id}.{screen_name}.{area_name}")

        if self._current_app_id and self._current_app_id != '_global' and self._current_app_id != app_id:
            to_try.append(f"{self._current_app_id}.{screen_name}.{area_name}")

        for key in to_try:
            area = self._screen_area_map.get(key, None)
            if area is not None:
                return area

        return None

    def save_screen(self, screen_info: ScreenInfo, app_id: str | None = None) -> None:
        """保存画面"""
        if screen_info.old_screen_id != screen_info.screen_id:
            old_app_id = getattr(screen_info, '_loaded_app_id', app_id)
            self.delete_screen(screen_info.old_screen_id, app_id=old_app_id, save=False)
        self._id_2_screen[screen_info.screen_id] = screen_info
        screen_info._loaded_app_id = app_id
        self.save(screen_id=screen_info.screen_id, app_id=app_id)

    def delete_screen(self, screen_id: str, app_id: str | None = None, save: bool = True) -> None:
        """删除一个画面"""
        if screen_id in self._id_2_screen:
            screen_info = self._id_2_screen[screen_id]
            actual_app_id = app_id or getattr(screen_info, '_loaded_app_id', None)
            del self._id_2_screen[screen_id]

            file_path = self.get_yml_file_path(screen_id, app_id=actual_app_id)
            if os.path.exists(file_path):
                os.remove(file_path)

        if save:
            self.save(screen_id=screen_id, app_id=app_id)
        else:
            self.reload(from_memory=True)

    def save(self, screen_id: str | None = None, app_id: str | None = None, reload_after_save: bool = True) -> None:
        """保存到文件"""
        all_data = []

        for screen_info in self._id_2_screen.values():
            data = screen_info.to_dict()

            # 保存时恢复原始名称
            if hasattr(screen_info, '_original_screen_name'):
                data['screen_name'] = screen_info._original_screen_name

            all_data.append(data)

            if screen_id is not None and screen_id == screen_info.screen_id:
                target_app_id = app_id or getattr(screen_info, '_loaded_app_id', None)
                target_dir = self._get_screen_dir(target_app_id)
                os.makedirs(target_dir, exist_ok=True)

                file_name = screen_info._original_screen_name if hasattr(screen_info,
                                                                         '_original_screen_name') else screen_id
                file_path = os.path.join(target_dir, f'{file_name}.yml')
                with open(file_path, 'w', encoding='utf-8') as file:
                    yaml.safe_dump(data, file, allow_unicode=True, default_flow_style=False, sort_keys=False)

        with open(self.merge_yml_file_path, 'w', encoding='utf-8') as file:
            yaml.safe_dump(all_data, file, allow_unicode=True, default_flow_style=False, sort_keys=False)

        if reload_after_save:
            self.reload(from_memory=True)

    def init_screen_route(self) -> None:
        """初始化画面间的跳转路径（分离计算）"""
        # 1. 收集全局画面（没有命名空间或 namespace='_global'）
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

        # 2. 计算全局路径图（只包含全局画面之间的跳转）
        if global_screens:
            self._global_route_map = self._compute_routes(global_screens, app_id='_global')
        else:
            self._global_route_map = {}

        # 3. 计算各应用路径图（应用内画面 + 全局画面）
        self._app_route_maps.clear()
        for app_id, app_screens in app_screens_map.items():
            all_screens = app_screens + global_screens
            self._app_route_maps[app_id] = self._compute_routes(all_screens, app_id=app_id)

    def _compute_routes(self, screens: list[ScreenInfo], app_id: str = None) -> dict[str, dict[str, ScreenRoute]]:
        """
        计算给定画面列表的路径图

        Args:
            screens: 画面列表
            app_id: 应用ID（用于过滤跨应用跳转）
        """
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
                    # 尝试匹配目标画面
                    matched = self._find_target_screen(
                        goto_screen_name,
                        screen_map,
                        app_id=app_id,
                        from_screen=screen_info.screen_name
                    )

                    if matched is None:
                        # 只在非全局路径计算时报错
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
        """
        查找目标画面（支持命名空间自动补全）

        Args:
            target: 目标画面名称（可能是原始名称）
            screen_map: 可用画面映射
            app_id: 当前应用ID
            from_screen: 源画面名称（用于提取命名空间）
        """
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

            # 匹配画面名称
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
        self.reload(from_separated_files=True, app_id=app_id)
        log.info(f"加载了 {len(self.screen_info_list)} 个画面，{len(self._screen_area_map)} 个区域")