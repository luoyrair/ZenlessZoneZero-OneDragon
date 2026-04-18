from typing import Any

import cv2
from cv2.typing import MatLike

from one_dragon.base.geometry.rectangle import Rect
from one_dragon.base.screen.screen_area import ScreenArea


class ScreenInfo:

    def __init__(self, data: dict[str, Any]):
        self._loaded_app_id: str | None = None
        self._namespace: str | None = None  # 命名空间（应用ID）
        self._original_screen_name: str | None = None  # 原始画面名称（不带命名空间）

        self.old_screen_id: str = data.get('screen_id', '')
        self.screen_id: str = data.get('screen_id', '')

        # 处理画面名称：如果传入的已经是带命名空间的，尝试解析
        raw_screen_name: str = data.get('screen_name', '')
        if '.' in raw_screen_name and self._loaded_app_id is None:
            # 如果是从文件直接加载的带命名空间名称，解析它
            parts = raw_screen_name.split('.', 1)
            if len(parts) == 2:
                self._namespace = parts[0]
                self._original_screen_name = parts[1]
                self.screen_name = raw_screen_name  # 保持完整名称
            else:
                self.screen_name = raw_screen_name
        else:
            self.screen_name = raw_screen_name

        self.screen_image: MatLike | None = None

        self.pc_alt: bool = data.get('pc_alt', False)
        self.area_list: list[ScreenArea] = []

        data_area_list = data.get('area_list', [])
        for data_area in data_area_list:
            pc_rect = data_area.get('pc_rect')
            area = ScreenArea(
                area_name=data_area.get('area_name'),
                pc_rect=Rect(pc_rect[0], pc_rect[1], pc_rect[2], pc_rect[3]),
                text=data_area.get('text'),
                lcs_percent=data_area.get('lcs_percent'),
                template_id=data_area.get('template_id'),
                template_sub_dir=data_area.get('template_sub_dir'),
                template_match_threshold=data_area.get('template_match_threshold'),
                color_range=data_area.get('color_range'),
                pc_alt=self.pc_alt,
                id_mark=data_area.get('id_mark', False),
                goto_list=data_area.get('goto_list', []),
                gamepad_key=data_area.get('gamepad_key', ''),
            )
            self.area_list.append(area)

    def get_image_to_show(self, highlight_area_idx: int | None = None) -> MatLike:
        """用于显示的图片"""
        if self.screen_image is None:
            return None

        image = self.screen_image.copy()
        for idx, area in enumerate(self.area_list):
            if highlight_area_idx is not None and idx == highlight_area_idx:
                color = (0, 0, 255)
                thickness = 4
            else:
                color = (255, 0, 0)
                thickness = 2

            half_thickness = thickness // 2
            outer_x1 = area.pc_rect.x1 - half_thickness
            outer_y1 = area.pc_rect.y1 - half_thickness
            outer_x2 = area.pc_rect.x2 + half_thickness
            outer_y2 = area.pc_rect.y2 + half_thickness

            img_height, img_width = image.shape[:2]
            outer_x1 = max(0, outer_x1)
            outer_y1 = max(0, outer_y1)
            outer_x2 = min(img_width - 1, outer_x2)
            outer_y2 = min(img_height - 1, outer_y2)

            if outer_x2 > outer_x1 and outer_y2 > outer_y1:
                cv2.rectangle(image,
                              (outer_x1, outer_y1),
                              (outer_x2, outer_y2),
                              color, thickness)

        return image

    def remove_area_by_idx(self, idx: int) -> None:
        """删除某行数据"""
        if self.area_list is None:
            return
        length = len(self.area_list)
        if idx < 0 or idx >= length:
            return
        self.area_list.pop(idx)

    def set_namespace(self, namespace: str, original_name: str) -> None:
        """
        设置命名空间

        Args:
            namespace: 命名空间（应用ID）
            original_name: 原始画面名称（不带命名空间）
        """
        self._namespace = namespace
        self._original_screen_name = original_name
        if namespace != '_global':
            self.screen_name = f"{namespace}.{original_name}"
        else:
            self.screen_name = original_name

    @property
    def display_name(self) -> str:
        """获取显示名称（不带命名空间，用于 UI 展示）"""
        if self._original_screen_name:
            return self._original_screen_name
        # 如果存储的是带命名空间的，尝试解析
        if '.' in self.screen_name:
            parts = self.screen_name.split('.', 1)
            return parts[1]
        return self.screen_name

    @property
    def namespace(self) -> str | None:
        """获取命名空间"""
        return self._namespace

    def to_dict(self) -> dict[str, Any]:
        """
        转换为字典（用于保存）
        保存时使用原始画面名称，不带命名空间
        """
        data: dict[str, Any] = {'screen_id': self.screen_id}

        # 保存时使用原始画面名称
        if self._original_screen_name:
            data['screen_name'] = self._original_screen_name
        else:
            # 兼容旧数据：如果 screen_name 带命名空间，尝试去掉
            if '.' in self.screen_name:
                parts = self.screen_name.split('.', 1)
                data['screen_name'] = parts[1]
            else:
                data['screen_name'] = self.screen_name

        data['pc_alt'] = self.pc_alt
        data['area_list'] = [area.to_dict() for area in self.area_list]

        return data

    def get_area(self, area_name: str) -> ScreenArea | None:
        """根据区域名称获取区域"""
        for area in self.area_list:
            if area.area_name == area_name:
                return area
        return None

    def __repr__(self) -> str:
        return f"ScreenInfo(screen_name={self.screen_name}, namespace={self._namespace}, original={self._original_screen_name})"