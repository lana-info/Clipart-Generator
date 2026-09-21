import numpy as np
import pytest
from PIL import Image
from chroma_key import remove_chroma_key_automatic
from chroma_rim import reclassify_rim


@pytest.mark.parametrize('key,index', [('red',0),('green',1),('blue',2)])
def test_partially_covered_row_is_not_forced_opaque(key,index):
    background = np.zeros(3, np.float32)
    background[index] = 255
    foreground = np.array([180,160,120], np.float32)
    foreground[index] = 40
    rgb = np.broadcast_to(background, (64,64,3)).copy()
    rgb[16:48,16:48] = foreground
    rgb[16,16:48] = np.rint(.8*foreground+.2*background)
    source = Image.fromarray(rgb.astype(np.uint8))
    result = np.asarray(remove_chroma_key_automatic(source,key,subject_profile='opaque_clipart'))
    assert abs(int(result[16,32,3])-204) <= 2
    assert np.max(np.abs(result[16,32,:3].astype(float)-foreground)) <= 3
    assert np.all(result[20:44,20:44,3] == 255)


@pytest.mark.parametrize('size',[1,2,4,16])
def test_isolated_small_details_are_not_removed_or_recoloured(size):
    source = np.full((80,80,3), [0,0,255], np.uint8)
    source[10:50,10:50] = [200,100,50]
    source[30:30+size,51:51+size] = [120,60,132]
    provisional = np.zeros((80,80,4), np.uint8)
    provisional[10:50,10:50] = [200,100,50,255]
    provisional[30:30+size,51:51+size] = [120,60,132,255]
    actual = reclassify_rim(Image.fromarray(source),Image.fromarray(provisional),np.array([0,0,255]))
    np.testing.assert_array_equal(actual,provisional)
