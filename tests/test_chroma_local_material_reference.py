"""A narrow pale petal must not inherit the colour of its connected centre."""
import numpy as np
import pytest
from PIL import Image, ImageDraw
from chroma_key import _remove_chroma_key_staged, remove_chroma_key_automatic


@pytest.mark.parametrize('key,channels', [('blue',(0,1,2)), ('green',(0,2,1)), ('red',(2,1,0))])
@pytest.mark.parametrize('centre', [(236,190,100),(230,203,138)])
def test_staged_textured_petal_keeps_its_source_colour(key, channels, centre):
    source = Image.new('RGB', (96,96), (1,6,247))
    draw = ImageDraw.Draw(source)
    draw.ellipse((30,16,86,82), fill=centre)
    draw.ellipse((15,25,55,39), fill=(244,237,229))
    pixels = np.array(source)
    petal = np.all(pixels == (244,237,229), axis=2)
    y,x = np.indices(petal.shape)
    shading = (x*3+y*5)%9-4
    pixels[petal] = pixels[petal].astype(np.int16)+shading[petal,None]
    pixels = pixels[...,channels]
    result = np.asarray(_remove_chroma_key_staged(Image.fromarray(pixels),key,opaque_subject=True))
    np.testing.assert_array_equal(result[petal,:3],pixels[petal])
    assert np.all(result[petal,3] == 255)
    assert np.all(result[:10,:,3] == 0)


@pytest.mark.parametrize('key,channels', [('blue',(0,1,2)), ('green',(0,2,1)), ('red',(2,1,0))])
@pytest.mark.parametrize('coverage', [0.8, 0.85])
@pytest.mark.parametrize('brightness', [1.0, 0.9])
def test_nearest_interior_sample_with_key_mix_is_not_an_opaque_colour(key, channels, coverage, brightness):
    background = np.array((20,45,240))
    colour = np.array((240,210,155))
    edge_colour = np.rint(brightness * colour)
    source = np.full((96,96,3), background, dtype=np.uint8)
    source[20:76,20:76] = np.rint(coverage*edge_colour+(1-coverage)*background)
    source[23:73,23:73] = colour
    result = np.asarray(remove_chroma_key_automatic(
        Image.fromarray(source[...,channels]),key,subject_profile='opaque_clipart'))
    np.testing.assert_allclose(result[20,40,:3],edge_colour[list(channels)],atol=2)
    assert abs(int(result[20,40,3])-round(coverage*255)) <= 2


@pytest.mark.parametrize('key,channels', [('blue',(0,1,2)), ('green',(0,2,1)), ('red',(2,1,0))])
@pytest.mark.parametrize('width', [3,6,8])
@pytest.mark.parametrize('edge_colour', [(240,210,155),(216,189,140),(236,214,151)])
def test_wide_or_textured_key_mixture_does_not_become_opaque(key, channels, width, edge_colour):
    background = np.array((20,45,240))
    source = np.full((96,96,3), background, dtype=np.uint8)
    source[20:76,20:76] = np.rint(0.8*np.array(edge_colour)+0.2*background)
    source[20+width:76-width,20+width:76-width] = (240,210,155)
    result = np.asarray(remove_chroma_key_automatic(
        Image.fromarray(source[...,channels]),key,subject_profile='opaque_clipart'))
    # Known coverage allows the staged solver's texture/byte rounding error;
    # treating this band as opaque creates an error of 51 alpha levels.
    np.testing.assert_allclose(result[20,40,:3],np.array(edge_colour)[list(channels)],atol=5)
    assert abs(int(result[20,40,3])-204) <= 8


@pytest.mark.parametrize('key,channels', [('blue',(0,1,2)), ('green',(0,2,1)), ('red',(2,1,0))])
@pytest.mark.parametrize('width', [13,14])
def test_clean_sample_beyond_fixed_depth_is_still_considered(key, channels, width):
    background = np.array((20,45,240))
    colour = np.array((240,210,155))
    source = np.full((96,96,3), background, dtype=np.uint8)
    source[20:76,20:76] = np.rint(0.8*colour+0.2*background)
    source[20+width:76-width,20+width:76-width] = colour
    result = np.asarray(remove_chroma_key_automatic(
        Image.fromarray(source[...,channels]),key,subject_profile='opaque_clipart'))
    # This wider band has greater uncertainty in the existing staged solution,
    # but must still retain fractional coverage and substantially remove key.
    # HEAD already has up to fifteen RGB levels of error on the 14px fixture.
    np.testing.assert_allclose(result[20,40,:3],colour[list(channels)],atol=16)
    assert abs(int(result[20,40,3])-204) <= 10


@pytest.mark.parametrize('key,channels', [('blue',(0,1,2)), ('green',(0,2,1)), ('red',(2,1,0))])
def test_impossible_key_mixture_does_not_veto_a_bright_local_material(key, channels):
    source = Image.new('RGB',(96,96),(1,6,247))
    draw = ImageDraw.Draw(source)
    draw.rectangle((25,16,86,82),fill=(230,203,138))
    draw.rectangle((15,25,40,30),fill=(248,240,228))
    pixels = np.array(source)
    pale = np.all(pixels == (248,240,228),axis=2)
    y,x = np.indices(pale.shape)
    shading = (x*3+y*5)%5-2
    pixels[pale] = pixels[pale].astype(np.int16)+shading[pale,None]
    pixels = pixels[...,channels]
    result = np.asarray(_remove_chroma_key_staged(Image.fromarray(pixels),key,opaque_subject=True))
    np.testing.assert_array_equal(result[pale,:3],pixels[pale])
    assert np.all(result[pale,3] == 255)


@pytest.mark.parametrize('key,channels', [('blue',(0,1,2)), ('green',(0,2,1)), ('red',(2,1,0))])
def test_ambiguous_bright_edge_paint_keeps_source_colour(key, channels):
    source = np.full((96,96,3),(20,45,240),dtype=np.uint8)
    source[20:76,20:76] = (244,219,203)
    source[23:73,23:73] = (240,210,155)
    edge = np.zeros((96,96),bool)
    edge[20:76,20:76] = True
    edge[23:73,23:73] = False
    pixels = source[...,channels]
    result = np.asarray(remove_chroma_key_automatic(
        Image.fromarray(pixels),key,subject_profile='opaque_clipart'))
    # Identical RGB could instead be opaque pigment plus additive key light.
    # With no evidence distinguishing those, preserve the painted-edge case.
    np.testing.assert_array_equal(result[edge,:3],pixels[edge])
    assert np.all(result[edge,3] == 255)
