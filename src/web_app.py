"""Web UI: drop PDFs, have the API (src/api.py) process them, browse and download the results.

Start the API first, then the UI, both from the repo root:
  python -m uvicorn src.api:app --port 8000
  python -m streamlit run src/web_app.py
The UI holds no pipeline: everything goes through the API at API_URL.
"""

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import streamlit as st

API_URL = "http://localhost:8000"
TIMEOUT_S = 600.0  # a batch of scans can take minutes


class ApiUnavailable(Exception):
    """The API cannot be reached or answered with an error."""


def call_api(method: str, path: str, **kwargs: Any) -> Any:
    try:
        response = httpx.request(method, f"{API_URL}{path}", timeout=TIMEOUT_S, **kwargs)
    except httpx.TransportError as error:
        raise ApiUnavailable(f"Brak połączenia z API ({API_URL}): {error}") from error
    if response.is_error:
        raise ApiUnavailable(f"API odpowiedziało {response.status_code}: {response.text[:300]}")
    return response.json()


def process(files: list, experiment: str) -> list[dict[str, Any]]:
    with st.spinner(f"Przetwarzanie {len(files)} plików…"):
        body = call_api("POST", "/documents", params={"experiment": experiment},
                        files=[("files", (file.name, file.getvalue(), "application/pdf")) for file in files])
    return body["documents"]


def output_json(document: dict[str, Any]) -> str:
    return json.dumps(document["data"], ensure_ascii=False, indent=2)


def results_zip(documents: list[dict[str, Any]]) -> bytes:
    """All output JSONs (as the challenge expects them) and their traces; repeated file names get a number."""
    buffer, used = io.BytesIO(), set()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for index, document in enumerate(documents, start=1):
            stem = Path(document["file_name"]).stem
            name = stem if stem not in used else f"{stem}_{index}"
            used.add(name)
            trace = {key: document[key] for key in ("file_name", "doc_type", "classification_scores", "error", "sources")}
            archive.writestr(f"output/{name}.json", output_json(document))
            archive.writestr(f"traces/{name}.json", json.dumps(trace, ensure_ascii=False, indent=2))
    return buffer.getvalue()


def show_document(index: int, document: dict[str, Any], expanded: bool) -> None:
    title = f"{document['file_name']} → {document['doc_type'] or 'nierozpoznany ({})'} · {document['elapsed_s']:.1f} s"
    with st.expander(title, expanded=expanded):
        if document["error"]:
            st.error(f"Nie udało się przetworzyć: {document['error']}")
        if scores := document["classification_scores"]:
            st.caption("Punkty klasyfikacji: " + ", ".join(f"{name} {score:g}" for name, score in scores.items()))
        output_tab, sources_tab = st.tabs(["JSON", "Pochodzenie wartości"])
        with output_tab:
            st.json(document["data"])
            st.download_button("Pobierz JSON", output_json(document), file_name=f"{Path(document['file_name']).stem}.json",
                               mime="application/json", key=f"download-{index}")
        with sources_tab:
            if document["sources"]:
                st.dataframe(pd.DataFrame([{"pole": source["path"], "wartość": str(source["value"]),
                                            "źródło": source["source"], "reguła": source["detail"],
                                            "strona": source["page"], "fragment": source["snippet"]}
                                           for source in document["sources"]]),
                             hide_index=True, use_container_width=True)
            else:
                st.write("Brak wyodrębnionych wartości.")


def main() -> None:
    st.set_page_config(page_title="Odwołania2json", page_icon="📄", layout="wide")
    st.title("Odwołania2json")
    st.write("Odwołanie, pełnomocnictwo lub potwierdzenie przelewu (PDF) → JSON. Inne dokumenty dają `{}`.")
    try:
        experiments = call_api("GET", "/experiments")
    except ApiUnavailable as error:
        st.error(f"{error}\n\nUruchom API: `python -m uvicorn src.api:app --port 8000`")
        return

    names = [experiment["name"] for experiment in experiments]
    default = next(index for index, experiment in enumerate(experiments) if experiment["default"])
    chosen = experiments[names.index(st.sidebar.selectbox("Wariant potoku", names, index=default))]
    st.sidebar.caption(chosen["description"])
    st.sidebar.caption(f"LLM: {chosen['llm_model'] or 'brak (same reguły)'}")
    st.sidebar.caption(f"API: {API_URL} · [Swagger]({API_URL}/docs)")

    files = st.file_uploader("Pliki PDF", type="pdf", accept_multiple_files=True)
    if st.button("Przetwórz", type="primary", disabled=not files):
        try:
            st.session_state.documents = process(files, chosen["name"])
        except ApiUnavailable as error:
            st.error(str(error))

    documents: list[dict[str, Any]] = st.session_state.get("documents", [])
    if not documents:
        return
    recognised = sum(document["doc_type"] is not None for document in documents)
    st.subheader(f"Wyniki: {len(documents)} plików, rozpoznane {recognised}")
    st.download_button("Pobierz wszystko (ZIP)", results_zip(documents), file_name="odwolania2json.zip",
                       mime="application/zip")
    for index, document in enumerate(documents):
        show_document(index, document, expanded=len(documents) == 1)


main()
