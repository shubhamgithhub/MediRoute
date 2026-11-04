from pathlib import Path
import pymupdf


MIN_TEXT_LENGTH = 20


class PDFParser:

    def parse_pdf_bytes(
        self,
        file_bytes: bytes,
        filename: str
    ) -> dict:

        if not file_bytes:
            return {
                "filename": filename,
                "status": "error",
                "reason": "Empty file",
                "page_count": 0,
                "text_length": 0,
                "text": ""
            }

        try:

            document = pymupdf.open(
                stream=file_bytes,
                filetype="pdf"
            )

        except Exception as exc:

            return {
                "filename": filename,
                "status": "error",
                "reason": f"Unable to open PDF: {str(exc)}",
                "page_count": 0,
                "text_length": 0,
                "text": ""
            }

        extracted_pages = []

        try:

            for page_number, page in enumerate(
                document,
                start=1
            ):

                text = page.get_text(
                    "text",
                    sort=True
                )

                extracted_pages.append(
                    {
                        "page_number": page_number,
                        "text": text.strip()
                    }
                )

            combined_text = "\n\n".join(
                page["text"]
                for page in extracted_pages
                if page["text"]
            ).strip()

            page_count = len(document)

        finally:
            document.close()

        # Very little or no extractable text usually means
        # scanned/image-only PDF or an unreadable document.
        if len(combined_text) < MIN_TEXT_LENGTH:

            return {
                "filename": filename,
                "status": "needs_ocr",
                "reason": (
                    "PDF contains little or no "
                    "extractable text"
                ),
                "page_count": page_count,
                "text_length": len(combined_text),
                "pages": extracted_pages,
                "text": combined_text
            }

        return {
            "filename": filename,
            "status": "success",
            "reason": None,
            "page_count": page_count,
            "text_length": len(combined_text),
            "pages": extracted_pages,
            "text": combined_text
        }
        
    def parse_multiple_pdfs(
        self,
        files: list[tuple[str, bytes]]
    ) -> dict:

        documents = []

        for filename, file_bytes in files:

            result = self.parse_pdf_bytes(
                file_bytes=file_bytes,
                filename=filename
            )

            documents.append(result)

        successful_files = sum(
            1
            for document in documents
            if document["status"] == "success"
        )

        needs_ocr_files = sum(
            1
            for document in documents
            if document["status"] == "needs_ocr"
        )

        error_files = sum(
            1
            for document in documents
            if document["status"] == "error"
        )

        combined_text_parts = []

        for document in documents:

            if (
                document["status"] == "success"
                and document["text"]
            ):

                combined_text_parts.append(
                    f"\n--- FILE: "
                    f"{document['filename']} ---\n"
                    f"{document['text']}"
                )

        combined_text = "\n".join(
            combined_text_parts
        ).strip()
        if len(documents) == 0:
            overall_status = "error"

        elif successful_files == len(documents):
            overall_status = "success"

        elif successful_files > 0:
            overall_status = "partial_success"

        elif needs_ocr_files > 0:
            overall_status = "needs_ocr"

        else:
            overall_status = "error"
        return {
            "overall_status": overall_status,
            "total_files": len(documents),
            "successful_files": successful_files,
            "needs_ocr_files": needs_ocr_files,
            "error_files": error_files,
            "documents": documents,
            "combined_text": combined_text
        }