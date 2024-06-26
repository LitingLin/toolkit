""" Rasterization of regions. This module contains functions for rasterizing different region types."""

from typing import List, Tuple, Optional

import numba
import numpy as np

_TYPE_EMPTY = 0
_TYPE_RECTANGLE = 1
_TYPE_POLYGON = 2
_TYPE_MASK = 3

@numba.njit(cache=True)
def mask_bounds(mask: np.ndarray):
    """ Compute bounds of a binary mask. Bounds are defined as the minimal axis-aligned region containing all positive pixels.
    This is a Numba implementation of the function that is compiled to machine code for faster execution.

    Args:
        mask (np.ndarray): 2-D array with a binary mask

    Returns:
        coordinates of the top-left and bottom-right corners of the minimal axis-aligned region containing all positive pixels
    """
    ii32 = np.iinfo(np.int32)
    top = ii32.max
    bottom = ii32.min
    left = ii32.max
    right = ii32.min

    for i in range(mask.shape[0]):
        for j in range(mask.shape[1]):
            if mask[i, j] != 0:
                top = min(top, i)
                bottom = max(bottom, i)
                left = min(left, j)
                right = max(right, j)

    if top == ii32.max:
        return (0, 0, 0, 0)

    return (left, top, right, bottom)


@numba.njit(cache=True)
def rasterize_rectangle(data: np.ndarray, bounds: Tuple[int, int, int, int]):
    """ Rasterize a rectangle. This is a Numba implementation of the function that is compiled to machine code for faster execution.

    Args:
        data: 4x1 array with rectangle coordinates (x, y, width, height)
        bounds: 4-tuple with the bounds of the image (left, top, right, bottom)

    Returns:
        2-D array with the rasterized rectangle
    """
    width = bounds[2] - bounds[0] + 1
    height = bounds[3] - bounds[1] + 1

    mask = np.zeros((height, width), dtype=np.uint8)

    if data[0, 0] > bounds[2] or data[0, 0] + data[2, 0] - 1 < bounds[0] or data[1, 0] > bounds[3] or data[1, 0] + data[3, 0] - 1 < bounds[1]:
        return mask

    left = max(0, data[0, 0] - bounds[0])
    top = max(0, data[1, 0] - bounds[1])
    right = min(bounds[2], data[0, 0] + data[2, 0] - 1 - bounds[0])
    bottom = min(bounds[3], data[1, 0] + data[3, 0] - 1 - bounds[1])

    mask[top:bottom+1, left:right+1] = 1

    return mask

@numba.njit(cache=True)
def rasterize_polygon(data: np.ndarray, bounds: Tuple[int, int, int, int]):
    """ Rasterize a polygon. This is a Numba implementation of the function that is compiled to machine code for faster execution.

    Args:
        data: Nx2 array with polygon coordinates
        bounds: 4-tuple with the bounds of the image (left, top, right, bottom)

    Returns:
        2-D array with the rasterized polygon
    """

    #int nodes, pixelY, i, j, swap;
    #region_polygon polygon = polygon_input;
    count = data.shape[0]

    width = bounds[2] - bounds[0] + 1
    height = bounds[3] - bounds[1] + 1

    nodeX = np.zeros((count, ), dtype=np.int64)
    mask = np.zeros((height, width), dtype=np.uint8)

    polygon = np.empty_like(data)
    np.round(data, 0, polygon)

    polygon = polygon - np.array([[bounds[0], bounds[1]]])

    #  Loop through the rows of the image.
    for pixelY in range(height):

        #  Build a list of nodes.
        nodes = 0
        j = count - 1

        for i in range(count):
            if (((polygon[i, 1] <= pixelY) and (polygon[j, 1] > pixelY)) or
                    ((polygon[j, 1] <= pixelY) and (polygon[i, 1] > pixelY)) or
                    ((polygon[i, 1] < pixelY) and (polygon[j, 1] >= pixelY)) or
                    ((polygon[j, 1] < pixelY) and (polygon[i, 1] >= pixelY)) or
                    ((polygon[i, 1] == polygon[j, 1]) and (polygon[i, 1] == pixelY))):
                r = (polygon[j, 1] - polygon[i, 1])
                k = (polygon[j, 0] - polygon[i, 0])
                if r != 0:
                    nodeX[nodes] = (polygon[i, 0] + (pixelY - polygon[i, 1]) / r * k)
                else:
                    nodeX[nodes] = polygon[i, 0]
                nodes = nodes + 1
            j = i

        # Sort the nodes, via a simple “Bubble” sort.
        i = 0
        while (i < nodes - 1):
            if nodeX[i] > nodeX[i + 1]:
                swap = nodeX[i]
                nodeX[i] = nodeX[i + 1]
                nodeX[i + 1] = swap
                if (i):
                    i = i - 1
            else:
                i = i + 1

        #  Fill the pixels between node pairs.
        i = 0
        while i < nodes - 1:
            if nodeX[i] >= width:
                break
            # If a point is in the line then we get two identical values
            # Ignore the first, except when it is the last point in vector
            if (nodeX[i] == nodeX[i + 1] and i < nodes - 2):
                i = i + 1
                continue

            if nodeX[i + 1] >= 0:
                if nodeX[i] < 0:
                    nodeX[i] = 0
                if nodeX[i + 1] >= width:
                    nodeX[i + 1] = width - 1
                for j in range(nodeX[i], nodeX[i + 1] + 1):
                    mask[pixelY, j] = 1
            i += 2

    return mask


@numba.njit(cache=True)
def copy_mask(mask: np.ndarray, offset: Tuple[int, int], bounds: Tuple[int, int, int, int]):
    """ Copy a mask to a new location. This is a Numba implementation of the function that is compiled to machine code for faster execution.
     
    Args:
        mask: 2-D array with the mask
        offset: 2-tuple with the offset of the mask
        bounds: 4-tuple with the bounds of the image (left, top, right, bottom)
        
    Returns:
        2-D array with the copied mask
    """

    tx = max(offset[0], bounds[0])
    ty = max(offset[1], bounds[1])

    ox = tx - bounds[0]
    oy = ty - bounds[1]
    gx = tx - offset[0]
    gy = ty - offset[1]

    tw = min(bounds[2] + 1, offset[0] + mask.shape[1]) - tx
    th = min(bounds[3] + 1, offset[1] + mask.shape[0]) - ty

    copy = np.zeros((bounds[3] - bounds[1] + 1, bounds[2] - bounds[0] + 1), dtype=np.uint8)

    for i in range(th):
        for j in range(tw):
            copy[i + oy, j + ox] = mask[i + gy, j + gx]

    return copy

@numba.njit(cache=True)
def _bounds_rectangle(a):
    """ Calculate the bounds of a rectangle. This is a Numba implementation of the function that is compiled to machine code for faster execution.
    
    Args:
        a: 4x1 array with the rectangle coordinates
        
    Returns:
        4-tuple with the bounds of the rectangle (left, top, right, bottom)
    """
    return (int(round(a[0, 0])), int(round(a[1, 0])), int(round(a[0, 0] + a[2, 0] - 1)), int(round(a[1, 0] + a[3, 0] - 1)))

@numba.njit(cache=True)
def _bounds_polygon(a):
    """ Calculate the bounds of a polygon. This is a Numba implementation of the function that is compiled to machine code for faster execution.
    
    Args:
        a: Nx2 array with the polygon coordinates
    
    Returns:
        4-tuple with the bounds of the polygon (left, top, right, bottom)
    """
    fi32 = np.finfo(np.float32)
    top = fi32.max
    bottom = fi32.min
    left = fi32.max
    right = fi32.min

    for i in range(a.shape[0]):
        top = min(top, a[i, 1])
        bottom = max(bottom, a[i, 1])
        left = min(left, a[i, 0])
        right = max(right, a[i, 0])
    return (int(round(left)), int(round(top)), int(round(right)), int(round(bottom)))

@numba.njit(cache=True)
def _bounds_mask(a, o):
    """ Calculate the bounds of a mask. This is a Numba implementation of the function that is compiled to machine code for faster execution.
    
    Args:
        a: 2-D array with the mask
        o: 2-tuple with the offset of the mask
        
    Returns:
        4-tuple with the bounds of the mask (left, top, right, bottom)
    """
    bounds = mask_bounds(a)
    return (bounds[0] + o[0], bounds[1] + o[1], bounds[2] + o[0], bounds[3] + o[1])

@numba.njit(cache=True)
def _region_bounds(a: np.ndarray, t: int, o: Optional[Tuple[int, int]] = None):
    """ Calculate the bounds of a region. This is a Numba implementation of the function that is compiled to machine code for faster execution.
    
    Args:
        a: 2-D array with the mask
        t: type of the region
        o: 2-tuple with the offset of the mask
        
    Returns:
        4-tuple with the bounds of the region (left, top, right, bottom)
    """
    if t == _TYPE_RECTANGLE:
        return _bounds_rectangle(a)
    elif t == _TYPE_POLYGON:
        return _bounds_polygon(a)
    elif t == _TYPE_MASK:
        return _bounds_mask(a, o)
    return (0, 0, 0, 0)

@numba.njit(cache=True)
def _region_raster(a: np.ndarray, bounds: Tuple[int, int, int, int], t: int, o: Optional[Tuple[int, int]] = None):
    """ Rasterize a region. This is a Numba implementation of the function that is compiled to machine code for faster execution.

    Args:
        a: 2-D array with the mask
        bounds: 4-tuple with the bounds of the image (left, top, right, bottom)
        t: type of the region
        o: 2-tuple with the offset of the mask
        
    Returns:
        2-D array with the rasterized region
    """

    if t == _TYPE_RECTANGLE:
        return rasterize_rectangle(a, bounds)
    elif t == _TYPE_POLYGON:
        return rasterize_polygon(a, bounds)
    elif t == _TYPE_MASK:
        return copy_mask(a, o, bounds)
    
    return np.zeros((bounds[3] - bounds[1] + 1, bounds[2] - bounds[0] + 1), dtype=np.uint8)

@numba.njit(cache=True)
def _calculate_overlap(a: np.ndarray, b: np.ndarray, at: int, bt: int, ao: Optional[Tuple[int, int]] = None,
        bo: Optional[Tuple[int, int]] = None, bounds: Optional[Tuple[int, int]] = None, ignore: Optional[np.array] = None, it: Optional[int] = None, io: Optional[Tuple[int, int]] = None):
    """ Calculate the overlap between two regions. This is a Numba implementation of the function that is compiled to machine code for faster execution.
    
    Args:
        a: 2-D array with the mask of the first region
        b: 2-D array with the mask of the second region
        at: type of the first region
        bt: type of the second region
        ao: 2-tuple with the offset of the first mask
        bo: 2-tuple with the offset of the second mask
        bounds: 2-tuple with the bounds of the image (left, top, right, bottom)
        ignore: 2-D array with the mask of the region to ignore
        it: type of the region to ignore
        io: 2-tuple with the offset of the mask to ignore
    
    Returns:
        float with the overlap between the two regions. Note that overlap is one by definition if both regions are empty.
    """

    bounds1 = _region_bounds(a, at, ao)
    bounds2 = _region_bounds(b, bt, bo)

    union = (min(bounds1[0], bounds2[0]), min(bounds1[1], bounds2[1]), max(bounds1[2], bounds2[2]), max(bounds1[3], bounds2[3]))

    if union[0] >= union[2] or union[1] >= union[3]:
        # Two empty regons are considered to be identical
        return float(1)

    if not bounds is None:
        raster_bounds = (max(0, union[0]), max(0, union[1]), min(bounds[0] - 1, union[2]), min(bounds[1] - 1, union[3]))
    else:
        raster_bounds = union

    if raster_bounds[0] >= raster_bounds[2] or raster_bounds[1] >= raster_bounds[3]:
        # Regions are not identical, but are outside rasterization bounds.
        return float(0)

    m1 = _region_raster(a, raster_bounds, at, ao)
    m2 = _region_raster(b, raster_bounds, bt, bo)

    a1 = m1.ravel()
    a2 = m2.ravel()

    intersection = 0
    union_ = 0

    if not ignore is None and it != _TYPE_EMPTY:
        m3 = _region_raster(ignore, raster_bounds, it, io)
        a3 = m3.ravel()
        for i in range(a1.size):
            if a3[i] == 0: # Non-negative value means that we ignore the pixel
                if a1[i] != 0 or a2[i] != 0:
                    union_ += 1
                    if a1[i] != 0 and a2[i] != 0:
                        intersection += 1
    else:
        for i in range(a1.size):
            if a1[i] != 0 or a2[i] != 0:
                union_ += 1
                if a1[i] != 0 and a2[i] != 0:
                    intersection += 1

    return float(intersection) / float(union_) if union_ > 0 else float(0)

from vot.region import Region, RegionException
from vot.region.shapes import Shape, Rectangle, Polygon, Mask

Bounds = Tuple[int, int]

def _infer_meta(reg: Region):
    if isinstance(reg, Rectangle):
        data1 = np.round(reg._data)
        offset1 = (0, 0)
        type1 = _TYPE_RECTANGLE
    elif isinstance(reg, Polygon):
        data1 = np.round(reg._points)
        offset1 = (0, 0)
        type1 = _TYPE_POLYGON
    elif isinstance(reg, Mask):
        data1 = reg.mask
        offset1 = reg.offset
        type1 = _TYPE_MASK
    else:
        data1 = np.zeros((1, 1))
        offset1 = (0, 0)
        type1 = _TYPE_EMPTY

    return data1, offset1, type1

def calculate_overlap(reg1: Shape, reg2: Shape, bounds: Optional[Bounds] = None, ignore: Optional[Shape] = None):
    """ Calculate the overlap between two regions. The function first rasterizes both regions to 2-D binary masks and calculates overlap between them

    Args:
        reg1: first region
        reg2: second region
        bounds: 2-tuple with the bounds of the image (width, height)
        ignore: region to ignore when calculating overlap, usually a mask

    Returns:
        float with the overlap between the two regions. Note that overlap is one by definition if both regions are empty.
    
    """

    data1, offset1, type1 = _infer_meta(reg1)
    data2, offset2, type2 = _infer_meta(reg2)

    if not ignore is None:
        ignore_data, ignore_offset, ignore_type = _infer_meta(ignore)
        return _calculate_overlap(data1, data2, type1, type2, offset1, offset2, bounds, ignore_data, ignore_type, ignore_offset)

    return _calculate_overlap(data1, data2, type1, type2, offset1, offset2, bounds)

def calculate_overlaps(first: List[Region], second: List[Region], bounds: Optional[Bounds] = None, ignore: Optional[List[Region]] = None):
    """ Calculate the overlap between two lists of regions. The function first rasterizes both regions to 2-D binary masks and calculates overlap between them

    Args:
        first: first list of regions
        second: second list of regions
        bounds: 2-tuple with the bounds of the image (width, height)
        ignore: list of regions to ignore when calculating overlap, usually a list of masks

    Returns:
        list of floats with the overlap between the two regions. Note that overlap is one by definition if both regions are empty.

    Raises:
        RegionException: if the lists are not of the same size
    """
    if not len(first) == len(second):
        raise RegionException("List not of the same size {} != {}".format(len(first), len(second)))
    
    if not ignore is None:
        if not len(first) == len(ignore):
            raise RegionException("List not of the same size {} != {}".format(len(first), len(ignore)))
        return [calculate_overlap(pairs[0], pairs[1], bounds=bounds, ignore=ignore[i]) for i, pairs in enumerate(zip(first, second))]
    return [calculate_overlap(pairs[0], pairs[1], bounds=bounds) for i, pairs in enumerate(zip(first, second))]
