"""
Core conversion: read a CAD file (IGES or STEP) and re-write it as **legacy
trimmed-surface IGES** (entity type 144) that older tube-CAM such as Tubes T
can import.

Background
----------
On ~18-Jul-2026 Onshape swapped its IGES export translator from Siemens'
Parasolid translator to Tech Soft 3D's HOOPS Exchange. The new engine emits a
manifold-solid B-Rep (entity 186 + analytic surfaces 190/192 + topology
502/504/508/510/514) which legacy tube-CAM cannot parse. The old engine emitted
trimmed parametric surfaces (144), which they can.

OpenCASCADE's IGES writer has a mode switch, ``write.iges.brep.mode``:
    0 = Faces  -> each face becomes a trimmed surface (144/143)   <- what we want
    1 = BRep   -> manifold solid B-Rep (186)                      <- what breaks
So the conversion is simply: read the shape, write it back in Faces mode.
"""
from __future__ import annotations

import gc
from pathlib import Path

from OCP.IGESControl import (
    IGESControl_Reader,
    IGESControl_Writer,
    IGESControl_Controller,
)
from OCP.STEPControl import STEPControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.ShapeFix import ShapeFix_Shape
from OCP.TopoDS import TopoDS_Shape


class ConversionError(Exception):
    """Raised for any user-facing conversion problem (bad/empty/unsupported file)."""


STEP_EXTS = {".step", ".stp"}
IGES_EXTS = {".igs", ".iges"}
SUPPORTED_EXTS = STEP_EXTS | IGES_EXTS


def _read_shape(path: Path) -> TopoDS_Shape:
    ext = path.suffix.lower()
    is_step = ext in STEP_EXTS
    reader = STEPControl_Reader() if is_step else IGESControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise ConversionError(
            f"Could not read '{path.name}' as {'STEP' if is_step else 'IGES'}."
        )
    reader.TransferRoots()
    shape = reader.OneShape()
    if shape.IsNull():
        raise ConversionError(f"'{path.name}' contained no usable geometry.")
    return shape


def _heal(shape: TopoDS_Shape) -> TopoDS_Shape:
    """Light repair pass — fixes small gaps/tolerance issues before re-export."""
    fixer = ShapeFix_Shape(shape)
    fixer.Perform()
    return fixer.Shape()


def convert_to_legacy_iges(src: Path | str, dst: Path | str) -> Path:
    """Read ``src`` (IGES/STEP) and write legacy trimmed-surface IGES to ``dst``.

    Returns the destination path. Raises :class:`ConversionError` on bad input.
    """
    src = Path(src)
    dst = Path(dst)
    if src.suffix.lower() not in SUPPORTED_EXTS:
        raise ConversionError(
            f"Unsupported file type '{src.suffix}'. Use .igs/.iges or .step/.stp."
        )
    try:
        shape = _read_shape(src)
        shape = _heal(shape)

        IGESControl_Controller.Init_s()
        # 0 = Faces (trimmed surfaces / 144); 1 = BRep (manifold solid / 186)
        Interface_Static.SetIVal_s("write.iges.brep.mode", 0)
        Interface_Static.SetCVal_s("write.iges.unit", "MM")
        Interface_Static.SetCVal_s("write.iges.header.author", "iges-converter")
        Interface_Static.SetCVal_s("write.iges.header.company", "Accora")

        writer = IGESControl_Writer("MM", 0)  # unit, mode(0 = Faces)
        writer.AddShape(shape)
        writer.ComputeModel()
        if not writer.Write(str(dst)):
            raise ConversionError("OpenCASCADE failed to write the IGES output.")
    finally:
        # Release OCC C++ objects promptly to keep the 512 MB instance happy.
        shape = None  # noqa: F841
        gc.collect()
    return dst
