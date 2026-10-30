"""Geometric and isolation controls for shared alpha edge operations."""
from concurrent.futures import CancelledError
from threading import Event

import numpy as np
import pytest
from PIL import Image

from studio_contour import BezierNode, BezierPath
from studio_edge_operations import edge_proposal, selection_scope


def path(shape=(64,64), fill=255):
    return BezierPath(tuple(BezierNode(p) for p in ((10,10),(50,10),(50,50),(10,50))),fill,shape)


def test_sharp_exact_original_numeric_contract_and_input_unchanged():
    values=np.array([[0,16,64,96,127,128,160,191,224,255]],dtype='uint8')
    mask=Image.fromarray(values)
    np.testing.assert_array_equal(np.asarray(edge_proposal(mask,'sharpen')),
                                  [[0,0,0,64,126,128,192,254,255,255]])
    np.testing.assert_array_equal(np.asarray(mask),values)


def test_smooth_improves_alias_circle_against_independent_analytic_coverage():
    y,x=np.indices((96,96));mask=(np.hypot(x-47.3,y-47.8)<=28.6).astype('uint8')*255
    reference=np.zeros(mask.shape,dtype=float)
    for dy in (np.arange(32)+.5)/32-.5:
        for dx in (np.arange(32)+.5)/32-.5:
            reference+=np.hypot(x+dx-47.3,y+dy-47.8)<=28.6
    reference*=255/1024
    smoothed=np.asarray(edge_proposal(Image.fromarray(mask),'smooth'))
    assert np.abs(smoothed-reference).mean()<np.abs(mask-reference).mean()
    assert (smoothed!=mask).any()
    np.testing.assert_array_equal(smoothed>=128,mask>=128)
    assert np.all(smoothed[mask==0]==0)
    assert np.all(smoothed[30:60,30:60]==255)


def test_straight_edge_is_not_blurred():
    mask=np.zeros((90,310),dtype='uint8');mask[:,125:]=255
    np.testing.assert_array_equal(np.asarray(edge_proposal(Image.fromarray(mask),'smooth')),mask)


def test_smoothing_reaches_fixed_point_and_retains_hole_and_thin_strokes():
    alpha=np.zeros((70,70),dtype='uint8');alpha[10:60,10:60]=255
    alpha[27:43,27:43]=0;alpha[4,4:40]=255;alpha[4:20,5]=255
    alpha[65,3:40]=66
    source=Image.fromarray(alpha);first=edge_proposal(source,'smooth')
    assert first.tobytes()==edge_proposal(first,'smooth').tobytes()
    result=np.asarray(first)
    np.testing.assert_array_equal(result>=128,alpha>=128)
    np.testing.assert_array_equal(result[65],alpha[65])
    assert np.all(result[alpha==0]==0)
    assert np.any(result[alpha==255]<255)


@pytest.mark.parametrize('value',[0,66,128,200,255])
def test_uniform_canvas_unchanged(value):
    mask=Image.new('L',(259,133),value)
    assert edge_proposal(mask,'smooth').tobytes()==mask.tobytes()


def test_tile_seams_match_same_shape_at_different_offsets():
    y,x=np.indices((350,350));base=(np.hypot(x-128,y-128)<70).astype('uint8')*255
    shifted=np.zeros_like(base);shifted[13:,17:]=base[:-13,:-17]
    a=np.asarray(edge_proposal(Image.fromarray(base),'smooth'))
    b=np.asarray(edge_proposal(Image.fromarray(shifted),'smooth'))
    np.testing.assert_array_equal(a[:337,:333],b[13:,17:])


@pytest.mark.parametrize('operation',['sharpen','smooth'])
def test_selected_run_does_not_touch_opposite_edges_or_other_objects(operation):
    value=255 if operation=='smooth' else 200
    alpha=np.zeros((64,64),dtype='uint8');alpha[10:51,10:51]=value
    alpha[7,56]=160
    p=path();selection=frozenset({(0,0),(0,1)})
    scope=np.asarray(selection_scope((64,64),(p,),selection))>0
    output=np.asarray(edge_proposal(Image.fromarray(alpha),operation,(p,),selection))
    np.testing.assert_array_equal(output[~scope],alpha[~scope])
    assert np.any(output[scope]!=alpha[scope])
    assert output[50,30]==value and output[7,56]==160


def test_single_node_and_disconnected_selection_never_bridge_unselected_arc():
    p=path();single=np.asarray(selection_scope((64,64),(p,),{(0,0)}))
    assert single[10,10]==255 and single[10,30]==0
    disjoint=np.asarray(selection_scope((64,64),(p,),{(0,0),(0,2)}))
    assert disjoint[10,10]==255 and disjoint[50,50]==255
    assert disjoint[10,30]==0 and disjoint[30,50]==0
    wrap=np.asarray(selection_scope((64,64),(p,),{(0,3),(0,0)}))
    assert wrap[30,10]==255 and wrap[30,50]==0


def test_selected_hole_edge_does_not_modify_exterior():
    alpha=np.zeros((64,64),dtype='uint8');alpha[5:59,5:59]=200;alpha[10:51,10:51]=0
    output=np.asarray(edge_proposal(Image.fromarray(alpha),'sharpen',(path(fill=0),),{(0,0),(0,1)}))
    assert output[9,30]==255 and output[5,30]==200


@pytest.mark.parametrize('selected',[{(1,0)},{(0,4)},{(-1,0)},{(False,0)},{(0,-1)}])
def test_invalid_selection_rejected_without_global_fallback(selected):
    mask=Image.new('L',(64,64),200);original=mask.tobytes()
    with pytest.raises(ValueError):edge_proposal(mask,'sharpen',(path(),),selected)
    assert mask.tobytes()==original


def test_wrong_shape_rejected():
    with pytest.raises(ValueError):edge_proposal(Image.new('L',(63,64)),'smooth',(path(),),{(0,0)})


def test_cancel_before_and_during_smoothing_never_mutates_input():
    y,x=np.indices((400,400));mask=Image.fromarray(((x+y)%3==0).astype('uint8')*255)
    original=mask.tobytes();event=Event();event.set()
    with pytest.raises(CancelledError):edge_proposal(mask,'smooth',cancelled=event)
    class Later:
        calls=0
        def is_set(self):
            self.calls+=1
            return self.calls>8
    with pytest.raises(CancelledError):edge_proposal(mask,'smooth',cancelled=Later())
    assert mask.tobytes()==original


def test_validation_preserves_inputs():
    with pytest.raises(ValueError):edge_proposal(Image.new('RGB',(5,5)),'smooth')
    with pytest.raises(ValueError):edge_proposal(Image.new('L',(5,5)),'unknown')


def test_existing_antialiased_edge_is_preserved_exactly():
    y,x=np.indices((96,96));coverage=np.zeros((96,96))
    for dy in (np.arange(32)+.5)/32-.5:
        for dx in (np.arange(32)+.5)/32-.5:
            coverage+=np.hypot(x+dx-47.3,y+dy-47.8)<=28.6
    alpha=np.rint(coverage*255/1024).astype('uint8')
    np.testing.assert_array_equal(np.asarray(edge_proposal(Image.fromarray(alpha),'smooth')),alpha)


def test_one_pixel_diagonal_and_isolated_paint_keep_visible_density():
    alpha=np.zeros((64,64),dtype='uint8');np.fill_diagonal(alpha,255);alpha[3,60]=255
    np.testing.assert_array_equal(np.asarray(edge_proposal(Image.fromarray(alpha),'smooth')),alpha)


def test_selected_curved_segment_follows_handles_not_chord():
    nodes=(BezierNode((10,30),out_handle=(10,0)),
           BezierNode((50,30),in_handle=(50,0)),BezierNode((30,50)))
    p=BezierPath(nodes,255,(64,64))
    scope=np.asarray(selection_scope((64,64),(p,),{(0,0),(0,1)}))
    assert scope[8,30]>0 and scope[30,30]==0 and scope[50,30]==0
