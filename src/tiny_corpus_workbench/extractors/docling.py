from __future__ import annotations

from pathlib import Path
from typing import Any

from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption


class DoclingConversionError(RuntimeError):
    pass


class DoclingSerializationError(RuntimeError):
    pass


def preflight() -> None:
    required = (
        callable(DocumentConverter),
        callable(PdfPipelineOptions),
        callable(PdfFormatOption),
        callable(AcceleratorOptions),
        callable(getattr(DocumentConverter, "convert", None)),
        hasattr(InputFormat, "PDF"),
        hasattr(ConversionStatus, "SUCCESS"),
        hasattr(ConversionStatus, "PARTIAL_SUCCESS"),
    )
    if not all(required):
        raise RuntimeError("Docling adapter API is incompatible")


def convert(source: Path, destination: Path, model_root: Path) -> tuple[str, dict[str, str]]:
    options = PdfPipelineOptions(
        artifacts_path=model_root.resolve(),
        do_ocr=False,
        do_table_structure=True,
        enable_remote_services=False,
        allow_external_plugins=False,
        accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU),
    )
    converter = DocumentConverter(
        allowed_formats=list(InputFormat),
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
    )
    try:
        result = converter.convert(source, raises_on_error=False)
    except Exception as error:
        raise DoclingConversionError(str(error)) from error
    upstream = result.status.value if hasattr(result.status, "value") else str(result.status)
    if result.status not in (ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS):
        raise DoclingConversionError(f"Docling upstream status: {upstream}")
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "document.json"
    markdown_path = destination / "document.md"
    try:
        result.document.save_as_json(json_path)
        result.document.save_as_markdown(markdown_path)
        if not json_path.stat().st_size or not markdown_path.read_text("utf-8").strip():
            raise DoclingSerializationError("Docling emitted an empty artifact")
        schema = result.document.model_dump(mode="json")
    except DoclingSerializationError:
        raise
    except Exception as error:
        raise DoclingSerializationError(str(error)) from error
    return upstream, {
        "name": str(schema.get("schema_name")),
        "version": str(schema.get("version")),
    }
