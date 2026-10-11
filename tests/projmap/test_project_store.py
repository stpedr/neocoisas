"""Esquema do projeto + salvar/carregar + .pmz (requisito 7)."""

import json
import zipfile

import pytest
from pydantic import ValidationError

from projmap.core.project import Project, Surface, default_project, parse_project
from projmap.core.state import ProjectState
from projmap.core.store import ProjectStore, media_kind_for

QUAD = [[100, 100], [500, 120], [520, 400], [90, 380]]


def _with_surface(store: ProjectStore, media_file) -> Project:
    project = store.load()
    item = store.add_media(media_file, media_file.name)
    project.media[item.sha256] = item
    project.surfaces.append(
        Surface(id="parede", label="Parede", node_id="proj-1", warp={"base": QUAD},
                source={"kind": "image", "media": item.sha256, "fit": "cover"}, feather=0.05)
    )
    store.save(project)
    return project


@pytest.fixture
def png(tmp_path):
    path = tmp_path / "foto parede.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 100)  # conteúdo não é decodificado aqui
    return path


def test_round_trip_salvar_carregar_identico(tmp_path, png):
    store = ProjectStore.create(tmp_path / "show.projmap", "Show")
    project = _with_surface(store, png)
    loaded = ProjectStore(store.root).load()
    assert loaded == project
    assert loaded.model_dump(mode="json") == json.loads(store.project_path.read_text("utf-8"))


def test_midia_por_hash_sem_duplicata(tmp_path, png):
    store = ProjectStore.create(tmp_path / "p")
    a = store.add_media(png, "a.png")
    b = store.add_media(png, "outro-nome.png")
    assert a.sha256 == b.sha256
    assert len(list((store.root / "media").iterdir())) == 1
    assert store.media_path(a).read_bytes() == png.read_bytes()


def test_formato_nao_suportado_e_arquivo_vazio(tmp_path):
    with pytest.raises(ValueError):
        media_kind_for("planilha.xlsx")
    store = ProjectStore.create(tmp_path / "p")
    empty = tmp_path / "vazio.mp4"
    empty.write_bytes(b"")
    with pytest.raises(ValueError):
        store.add_media(empty, empty.name)
    assert not any(p.name.startswith(".upload") for p in (store.root / "media").iterdir())


def test_quad_invalido_e_referencias_quebradas_sao_recusados():
    base = default_project().model_dump(mode="json")
    bad_quad = dict(base, surfaces=[{"id": "s", "node_id": "proj-1",
                                     "warp": {"base": [[0, 0], [10, 10], [10, 0], [0, 10]]}}])
    with pytest.raises(ValidationError):
        parse_project(bad_quad)
    orphan = dict(base, surfaces=[{"id": "s", "node_id": "nao-existe", "warp": {"base": QUAD}}])
    with pytest.raises(ValidationError, match="nó inexistente"):
        parse_project(orphan)
    no_media = dict(base, surfaces=[{"id": "s", "node_id": "proj-1", "warp": {"base": QUAD},
                                     "source": {"kind": "video", "media": "f" * 64}}])
    with pytest.raises(ValidationError, match="mídia desconhecida"):
        parse_project(no_media)
    with pytest.raises(ValidationError):
        parse_project(dict(base, campo_inventado=1))


def test_versao_futura_e_recusada():
    data = default_project().model_dump(mode="json")
    data["version"] = 99
    with pytest.raises(ValueError, match="mais nova"):
        parse_project(data)


def test_exportar_e_importar_pmz(tmp_path, png):
    store = ProjectStore.create(tmp_path / "orig")
    project = _with_surface(store, png)
    project.nodes[0].photo = store.set_photo("proj-1", b"\xff\xd8foto", "foto.jpg")
    store.save(project)

    pmz = store.export_pmz(tmp_path / "show.pmz")
    imported = ProjectStore.import_pmz(pmz, tmp_path / "copia")
    assert imported.load() == project
    item = next(iter(project.media.values()))
    assert imported.media_path(item).read_bytes() == png.read_bytes()
    assert imported.resolve(project.nodes[0].photo).read_bytes() == b"\xff\xd8foto"


def test_importar_recusa_zip_slip_e_midia_corrompida(tmp_path, png):
    evil = tmp_path / "evil.pmz"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../fora.txt", "x")
    with pytest.raises(ValueError, match="insegura"):
        ProjectStore.import_pmz(evil, tmp_path / "dest1")
    assert not (tmp_path / "fora.txt").exists()

    store = ProjectStore.create(tmp_path / "orig")
    project = _with_surface(store, png)
    pmz = store.export_pmz(tmp_path / "ok.pmz")
    item = next(iter(project.media.values()))
    corrupt = tmp_path / "corrupt.pmz"
    with zipfile.ZipFile(pmz) as src, zipfile.ZipFile(corrupt, "w") as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename.startswith("media/"):
                data = b"adulterado"
            dst.writestr(info.filename, data)
    with pytest.raises(ValueError, match="corrompida"):
        ProjectStore.import_pmz(corrupt, tmp_path / "dest2")
    del item


def test_resolve_recusa_caminho_fora_do_projeto(tmp_path):
    store = ProjectStore.create(tmp_path / "p")
    with pytest.raises(ValueError):
        store.resolve("../../etc/passwd")


def test_state_incrementa_revisao_e_persiste(tmp_path, png):
    store = ProjectStore.create(tmp_path / "p")
    state = ProjectState(store)
    rev0, _ = state.snapshot()

    def rename(p: Project) -> Project:
        p.name = "Renomeado"
        return p

    rev1 = state.update(rename)
    assert rev1 == rev0 + 1
    assert store.load().name == "Renomeado"

    def quebra(p: Project) -> Project:
        p.surfaces.append(Surface(id="x", node_id="fantasma", warp={"base": QUAD}))
        return p

    with pytest.raises(ValidationError):
        state.update(quebra)
    assert state.revision == rev1  # falha não publica nada
    assert store.load().name == "Renomeado"
