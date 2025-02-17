# Copyright (c) Facebook, Inc. and its affiliates. All rights reserved.

from typing import Tuple

import torch
from pytorch3d.transforms import Transform3d


def camera_to_eye_at_up(
    world_to_view_transform: Transform3d,
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """
    Given a world to view transform, return the eye, at and up vectors which
    represent its position.

    For example, if cam is a camera object, then after running

    .. code-block::

        from cameras import look_at_view_transform
        eye, at, up = camera_to_eye_at_up(cam.get_world_to_view_transform())
        R, T = look_at_view_transform(eye=eye, at=at, up=up)

    any other camera created from R and T will have the same world to view
    transform as cam.

    Also, given a camera position R and T, then after running:

    .. code-block::

        from cameras import get_world_to_view_transform, look_at_view_transform
        eye, at, up = camera_to_eye_at_up(get_world_to_view_transform(R=R, T=T))
        R2, T2 = look_at_view_transform(eye=eye, at=at, up=up)

    R2 will equal R and T2 will equal T.

    Args:
        world_to_view_transform: Transform3d representing the extrinsic
            transformation of N cameras.

    Returns:
        eye: FloatTensor of shape [N, 3] representing the camera centers in world space.
        at: FloatTensor of shape [N, 3] representing points in world space directly in
            front of the cameras e.g. the positions of objects to be viewed by the
            cameras.
        up: FloatTensor of shape [N, 3] representing vectors in world space which
            when projected on to the camera plane point upwards.
    """
    cam_trans = world_to_view_transform.inverse()
    # In the PyTorch3D right handed coordinate system, the camera in view space
    # is always at the origin looking along the +z axis.

    # The up vector is not a position so cannot be transformed with
    # transform_points. However the position eye+up above the camera
    # (whose position vector in the camera coordinate frame is an up vector)
    # can be transformed with transform_points.
    eye_at_up_view = torch.tensor(
        [[0, 0, 0], [0, 0, 1], [0, 1, 0]], dtype=torch.float32, device=cam_trans.device
    )
    eye_at_up_world = cam_trans.transform_points(eye_at_up_view).reshape(-1, 3, 3)

    eye, at, up_plus_eye = eye_at_up_world.unbind(1)
    up = up_plus_eye - eye
    return eye, at, up


def rotate_on_spot(
    R: torch.Tensor, T: torch.Tensor, rotation: torch.Tensor
) -> Tuple[torch.Tensor, torch.Tensor]:
    """
    Given a camera position as R and T (batched or not),
    and a rotation matrix (batched or not)
    return a new R and T representing camera position(s)
    in the same location but rotated on the spot by the
    given rotation. In particular the new world to view
    rotation will be the previous one followed by the inverse
    of the given rotation.

    For example, adding the following lines before constructing a camera
    will make the camera point a little to the right of where it
    otherwise would have been.

    .. code-block::

        from math import radians
        from pytorch3d.transforms import axis_angle_to_matrix
        angles = [0, radians(10), 0]
        rotation = axis_angle_to_matrix(torch.FloatTensor(angles))
        R, T = rotate_on_spot(R, T, rotation)

    Note here that if you have a column vector, then when you
    premultiply it by this `rotation` (see the rotation_conversions doc),
    then it will be rotated anticlockwise if facing the -y axis.
    In our context, where we postmultiply row vectors to transform them,
    `rotation` will rotate the camera clockwise around the -y axis
    (i.e. when looking down), which is a turn to the right.

    If angles was [radians(10), 0, 0], the camera would get pointed
    up a bit instead.

    If angles was [0, 0, radians(10)], the camera would be rotated anticlockwise
    a bit, so the image would appear rotated clockwise from how it
    otherwise would have been.

    If you want to translate the camera from the origin in camera
    coordinates, this is simple and does not need a separate function.
    In particular, a translation by X = [a, b, c] would cause
    the camera to move a units left, b units up, and c units
    forward. This is achieved by using T-X in place of T.

    Args:
        R: FloatTensor of shape [3, 3] or [N, 3, 3]
        T: FloatTensor of shape [3] or [N, 3]
        rotation: FloatTensor of shape [3, 3] or [n, 3, 3]
        where if neither n nor N is 1, then n and N must be equal.

    Returns:
        R: FloatTensor of shape [max(N, n), 3, 3]
        T: FloatTensor of shape [max(N, n), 3]
    """
    if R.ndim == 2:
        R = R[None]
    if T.ndim == 1:
        T = T[None]
    if rotation.ndim == 2:
        rotation = rotation[None]

    if R.ndim != 3 or R.shape[1:] != (3, 3):
        raise ValueError("Invalid R")
    if T.ndim != 2 or T.shape[1] != 3:
        raise ValueError("Invalid T")
    if rotation.ndim != 3 or rotation.shape[1:] != (3, 3):
        raise ValueError("Invalid rotation")

    new_R = R @ rotation.transpose(1, 2)
    old_RT = torch.bmm(R, T[:, :, None])
    new_T = torch.matmul(new_R.transpose(1, 2), old_RT)[:, :, 0]

    return new_R, new_T
