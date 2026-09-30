import pytest
from PIL import Image, ImageDraw
from chroma_key import detect_chroma_key_color, ChromaKeyAmbiguousError


@pytest.mark.parametrize('color,rgb', [('blue',(5,10,245)),('green',(7,240,12)),('red',(245,8,5))])
def test_auto_detects_rendered_color_without_using_subject(color, rgb):
    image = Image.new('RGB', (80, 80), rgb)
    ImageDraw.Draw(image).rectangle((8,8,71,71), fill='white')
    assert detect_chroma_key_color(image) == color


@pytest.mark.parametrize('rgb', ['white', 'black', 'gray', (120,115,130)])
def test_neutral_or_dark_background_requires_review(rgb):
    with pytest.raises(ChromaKeyAmbiguousError):
        detect_chroma_key_color(Image.new('RGB',(80,80),rgb))


def test_mixed_border_requires_review():
    image=Image.new('RGB',(80,80),'blue')
    ImageDraw.Draw(image).rectangle((0,0,39,79),fill='green')
    with pytest.raises(ChromaKeyAmbiguousError):
        detect_chroma_key_color(image)
