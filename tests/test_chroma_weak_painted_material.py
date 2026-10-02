"""Natural dark strokes must not borrow their neighbour's material hue."""
import numpy as np
import pytest
from PIL import Image
from chroma_key import remove_chroma_key_automatic

@pytest.mark.parametrize('key,channels', [('blue',(0,1,2)),('green',(0,2,1)),('red',(2,1,0))])
@pytest.mark.parametrize('width', [1,2,3])
def test_opaque_dark_painted_run_keeps_colour_at_every_stage(key,channels,width):
    source=np.full((96,96,3),(0,15,255),dtype=np.uint8)
    source[20:76,20:76]=(250,225,183)
    source[20:76,20:20+width]=(80,70,90)
    source=source[...,list(channels)];image=Image.fromarray(source)
    expected=np.column_stack((source[24:72,20],np.full(48,255,np.uint8)))
    stages=[]
    def observe(name,result):
        stages.append(name)
        np.testing.assert_array_equal(np.asarray(result)[24:72,20],expected,err_msg=name)
    result=remove_chroma_key_automatic(image,key,subject_profile='opaque_clipart',stage_observer=observe)
    assert 'precise_result' in stages and 'edge_chroma_repair' in stages
    np.testing.assert_array_equal(np.asarray(result)[24:72,20],expected)
    np.testing.assert_array_equal(np.asarray(image),source)
    assert not np.any(np.asarray(result)[:10,:,3])


@pytest.mark.parametrize('key,channels', [('blue',(0,1,2)),('green',(0,2,1)),('red',(2,1,0))])
@pytest.mark.parametrize('coverage,expected', [(.95,(145,115,137,255)),(.98,(142,113,139,255))])
def test_existing_weak_same_material_policy_remains_unchanged(key,channels,coverage,expected):
    # Preserve the established weak-mixture ambiguity policy; these expected
    # bytes are a compatibility check, not an assertion of ideal physical alpha.
    background=np.array((0,15,255));clean=np.array((145,115,137))
    source=np.full((96,96,3),background,dtype=np.uint8)
    source[20:76,20:76]=clean
    source[20:76,20:22]=np.rint(coverage*clean+(1-coverage)*background)
    result=remove_chroma_key_automatic(Image.fromarray(source[...,list(channels)]),key,subject_profile='opaque_clipart')
    np.testing.assert_array_equal(np.asarray(result)[40,20],np.array(expected)[list(channels)+[3]])


@pytest.mark.parametrize('alpha', [128,254])
def test_source_partial_alpha_is_never_promoted_by_paint_protection(alpha):
    source=np.full((96,96,4),(0,15,255,255),dtype=np.uint8)
    source[20:76,20:76]=(250,225,183,255)
    source[20:76,20:22]=(80,70,90,alpha)
    image=Image.fromarray(source)
    result=remove_chroma_key_automatic(image,'blue',subject_profile='opaque_clipart')
    assert np.all(np.asarray(result)[24:72,20:22,3]<=alpha)
    np.testing.assert_array_equal(np.asarray(image),source)


def test_parallel_images_do_not_share_protected_paint():
    from concurrent.futures import ThreadPoolExecutor
    images=[]
    for key,channels in [('blue',(0,1,2)),('green',(0,2,1)),('red',(2,1,0))]:
        source=np.full((96,96,3),(0,15,255),dtype=np.uint8)
        source[20:76,20:76]=(250,225,183)
        source[20:76,20:22]=(80,70,90) if key=='blue' else (145,115,137)
        images.append((Image.fromarray(source[...,list(channels)]),key))
    def run(pair):
        image,key=pair
        return np.asarray(remove_chroma_key_automatic(image,key,subject_profile='opaque_clipart'))
    expected=[run(pair) for pair in images]
    with ThreadPoolExecutor(max_workers=3) as executor:
        results=list(executor.map(run,images*3))
    for i,result in enumerate(results):
        np.testing.assert_array_equal(result,expected[i%3])
