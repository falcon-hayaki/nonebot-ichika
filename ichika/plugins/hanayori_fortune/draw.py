from PIL import Image, ImageDraw, ImageFont
import os
from pathlib import Path


class Draw:
    @classmethod
    async def draw_card(
        cls, resource_path: Path, pic_chosen: str, title: str, text: str, from_user: int
    ) -> str | None:
        font_path = {
            "title": str(resource_path / "font" / "Mamelon.otf"),
            "text": str(resource_path / "font" / "sakura.ttf"),
        }
        img = Image.open(pic_chosen)

        # Draw title
        draw = ImageDraw.Draw(img)
        font_size = 45
        color = "#F5F5F5"
        image_font_center = (140, 99)
        ttfront = ImageFont.truetype(font_path["title"], font_size)
        bbox = ttfront.getbbox(title)
        font_length = (bbox[2] - bbox[0], bbox[3] - bbox[1])
        draw.text(
            (
                image_font_center[0] - font_length[0] / 2,
                image_font_center[1] - font_length[1] / 2,
            ),
            title,
            fill=color,
            font=ttfront,
        )

        # Text rendering
        font_size = 25
        color = "#323232"
        image_font_center = [140, 297]
        ttfront = ImageFont.truetype(font_path["text"], font_size)
        result = cls.decrement(text)
        if not result[0]:
            return None
        for i in range(0, result[0]):
            font_height = len(result[i + 1]) * (font_size + 4)
            text_vertical = cls.vertical(result[i + 1])
            x = int(
                image_font_center[0]
                + (result[0] - 2) * font_size / 2
                + (result[0] - 1) * 4
                - i * (font_size + 4)
            )
            y = int(image_font_center[1] - font_height / 2)
            draw.text((x, y), text_vertical, fill=color, font=ttfront)

        # Save
        out_dir = resource_path / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = str(out_dir / f"{from_user}.png")
        img.save(out_path)
        return out_path

    @classmethod
    def decrement(cls, text: str) -> list:
        length = len(text)
        result = []
        cardinality = 9
        if length > 4 * cardinality:
            return [False]
        number_of_slices = 1
        while length > cardinality:
            number_of_slices += 1
            length -= cardinality
        result.append(number_of_slices)
        # Optimize for two columns
        space = " "
        length = len(text)
        if number_of_slices == 2:
            if length % 2 == 0:
                fill_in = space * int(9 - length / 2)
                return [
                    number_of_slices,
                    text[: int(length / 2)] + fill_in,
                    fill_in + text[int(length / 2) :],
                ]
            else:
                fill_in = space * int(9 - (length + 1) / 2)
                return [
                    number_of_slices,
                    text[: int((length + 1) / 2)] + fill_in,
                    fill_in + space + text[int((length + 1) / 2) :],
                ]
        for i in range(0, number_of_slices):
            if i == number_of_slices - 1 or number_of_slices == 1:
                result.append(text[i * cardinality :])
            else:
                result.append(text[i * cardinality : (i + 1) * cardinality])
        return result

    @classmethod
    def vertical(cls, s: str) -> str:
        return "\n".join(list(s))
