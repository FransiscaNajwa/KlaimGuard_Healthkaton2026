from typing import Any

from app.rag.vector_store import LocalVectorStore
from app.rag.vector_store import ChromaVectorManager


class RegulatoryCopilotService:
    def __init__(self, vector_store: LocalVectorStore):
        self.vector_store = vector_store

    def format_prompt(
        self, query: str, context_chunks: list[dict[str, Any]]
    ) -> str:
        context = "\n\n".join(
            f"[{chunk['source_document']} page {chunk['page_number']}]\n{chunk['text']}"
            for chunk in context_chunks
        )
        return (
            "Role: Legal and Medical Coding Advisor for BPJS Kesehatan.\n"
            "Answer only from the supplied excerpts. Do not invent clauses, facts, "
            "or page references. State when evidence is insufficient.\n"
            "Structure: Direct answer and coding analysis; official legal basis; "
            "quoted clause; formal dispute recommendation.\n\n"
            f"Question: {query}\n\nRegulation excerpts:\n{context}"
        )

    @staticmethod
    def _citation(chunk: dict[str, Any]) -> dict[str, Any]:
        excerpt = " ".join(chunk["text"].split())
        if len(excerpt) > 700:
            excerpt = f"{excerpt[:697].rsplit(' ', 1)[0]}..."
        return {
            "source_document": chunk["source_document"],
            "page_number": chunk["page_number"],
            "excerpt": excerpt,
        }

    def generate_answer(self, query: str) -> dict[str, Any]:
        context_chunks = self.vector_store.similarity_search(query, top_k=4)
        citations = [self._citation(chunk) for chunk in context_chunks]
        if not citations:
            answer = (
                "## Jawaban dan analisis koding\nTidak ditemukan kutipan regulasi "
                "yang cukup relevan untuk menjawab pertanyaan ini. Verifikator "
                "perlu meninjau dokumen sumber secara langsung.\n\n"
                "## Dasar hukum resmi\nBelum dapat ditentukan dari hasil pencarian.\n\n"
                "## Kutipan klausul\nTidak ada kutipan yang memenuhi pencarian."
            )
            letter = (
                "Draf sanggahan tidak dibuat karena tidak ditemukan dasar regulasi "
                "yang relevan. Verifikator perlu meninjau dokumen resmi terlebih dahulu."
            )
        else:
            source_lines = [
                f"- {item['source_document']}, halaman {item['page_number']}"
                for item in citations
            ]
            quote_lines = [
                f"> {item['excerpt']} [{index}]"
                for index, item in enumerate(citations, start=1)
            ]
            answer = (
                "## Jawaban dan analisis koding\n"
                "Berikut kutipan dokumen resmi yang paling relevan dengan "
                "pertanyaan. Kutipan ini menjadi bahan telaah; kesimpulan klaim "
                "tetap harus disesuaikan dengan resume medis dan kode yang ditagihkan.\n\n"
                "## Dasar hukum resmi\n"
                + "\n".join(source_lines)
                + "\n\n## Kutipan klausul regulasi\n"
                + "\n\n".join(quote_lines)
            )
            letter = (
                "Kepada Yth.\nKomite Audit Klinis Rumah Sakit\n\n"
                "Perihal: Permintaan klarifikasi koding klaim JKN\n\n"
                "Berdasarkan hasil telaah awal, kami memohon klarifikasi atas "
                "kesesuaian diagnosis dan/atau prosedur yang ditagihkan dengan "
                "resume medis serta ketentuan yang berlaku. Mohon disampaikan "
                "dokumen klinis pendukung dan penjelasan koding yang relevan.\n\n"
                "Rujukan dokumen:\n"
                + "\n".join(source_lines)
                + "\n\nDraf ini perlu diverifikasi dan disesuaikan oleh petugas "
                "sebelum dikirimkan secara resmi."
            )
        return {
            "answer_markdown": answer,
            "citations": citations,
            "drafted_dispute_letter": letter,
        }

    def draft_dispute_letter(
        self,
        claim_id: str,
        sep_number: str,
        primary_code: str,
        conflicting_code: str,
        violation_type: str,
        legal_source: str,
        regulation_ref: str,
        clinical_narrative: str,
        recommendation: str,
    ) -> dict[str, Any]:
        search_query = (
            f"{primary_code} {conflicting_code} {violation_type} "
            f"{clinical_narrative} {recommendation}"
        )
        evidence = self.generate_answer(search_query)
        citations = evidence["citations"]
        citation_text = "\n".join(
            f"- {item['source_document']}, halaman {item['page_number']}"
            for item in citations
        )
        if not citation_text:
            citation_text = f"- {legal_source}; {regulation_ref}"
        formal_letter = (
            "Kepada Yth.\nKomite Audit Klinis Rumah Sakit\n\n"
            f"Perihal: Klarifikasi klaim JKN {claim_id} (SEP {sep_number})\n\n"
            "Berdasarkan verifikasi awal, ditemukan ketidaksesuaian koding "
            f"{violation_type} pada pasangan kode {primary_code} dan "
            f"{conflicting_code}. Resume klinis yang menjadi dasar telaah: "
            f"{clinical_narrative}\n\n"
            f"Dasar hukum: {legal_source}; {regulation_ref}.\n"
            f"Rekomendasi koreksi: {recommendation}\n\n"
            f"Dokumen pendukung yang ditemukan:\n{citation_text}\n\n"
            "Mohon disampaikan klarifikasi dan dokumen klinis pendukung apabila "
            "terdapat bukti tambahan yang relevan. Draf ini wajib ditinjau dan "
            "disahkan oleh verifikator sebelum dikirimkan secara resmi."
        )
        return {"formal_letter": formal_letter, "citations": citations}


class RegulatoryRAGService:
    def __init__(self, vector_manager: ChromaVectorManager | None = None):
        self.vector_manager = vector_manager or ChromaVectorManager()

    def retrieve_legal_evidence(self, query: str, top_k: int = 3) -> dict[str, Any]:
        matches = self.vector_manager.query_similar_regulations(query, top_k=top_k)
        citations = [
            {
                "source_document": item["source_document"],
                "page_number": item["page_number"],
                "excerpt": " ".join(item["text"].split())[:700],
                "similarity_score": item["similarity_score"],
            }
            for item in matches
        ]
        legal_grounding = "\n\n".join(
            f"[{item['source_document']} page {item['page_number']}] {item['text']}"
            for item in matches
        )
        return {
            "query": query,
            "matches": matches,
            "citations": citations,
            "legal_grounding": legal_grounding,
        }

    def draft_dispute_argument(
        self,
        claim_id: str,
        primary_code: str,
        conflicting_code: str,
        violation_type: str,
    ) -> dict[str, Any]:
        query = (
            f"{primary_code} {conflicting_code} {violation_type} "
            "kaidah koding solusi sengketa prosedur inklusif"
        )
        evidence = self.retrieve_legal_evidence(query, top_k=4)
        citation_lines = [
            f"- {item['source_document']}, halaman {item['page_number']}"
            for item in evidence["citations"]
        ]
        recommended_actions = []
        for match in evidence["matches"]:
            for line in match["text"].splitlines():
                normalized = line.casefold()
                if any(term in normalized for term in ("solusi", "rekomendasi", "hapus kode")):
                    action = line.strip(" \t:-")[:300]
                    if action and action not in recommended_actions:
                        recommended_actions.append(action)
        if not recommended_actions:
            recommended_actions.append(
                "Cocokkan kode dan dokumentasi klinis dengan kutipan resmi; "
                "verifikator menetapkan koreksi akhir."
            )
        formal_letter = (
            "Kepada Yth.\nKomite Audit Klinis Rumah Sakit\n\n"
            f"Perihal: Klarifikasi klaim JKN {claim_id}\n\n"
            "Berdasarkan telaah awal, diperlukan klarifikasi atas pasangan kode "
            f"{primary_code} dan {conflicting_code} dengan jenis telaah "
            f"{violation_type}. Mohon disampaikan resume medis serta dokumen "
            "pendukung yang menjelaskan dasar penetapan kode tersebut.\n\n"
            "Rujukan dokumen resmi:\n"
            + ("\n".join(citation_lines) if citation_lines else "Tidak ditemukan kutipan relevan.")
            + "\n\nDraf ini wajib diperiksa dan disahkan verifikator sebelum "
            "dikirimkan secara resmi."
        )
        return {
            "formal_letter": formal_letter,
            "legal_citations": evidence["citations"],
            "recommended_actions": recommended_actions,
            "evidence": evidence["matches"],
        }