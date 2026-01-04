import importlib.util
from pathlib import Path


def _load_helper():
    spec = importlib.util.spec_from_file_location(
        "run_local_helper",
        Path(__file__).resolve().parents[1] / "scripts" / "run_local.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_find_site_packages_dir_windows(tmp_path):
    module = _load_helper()
    windows_site = tmp_path / "Lib" / "site-packages"
    windows_site.mkdir(parents=True)
    assert module._find_site_packages_dir(tmp_path) == windows_site


def test_find_site_packages_dir_unix(tmp_path):
    module = _load_helper()
    lib_root = tmp_path / "lib" / "python3.11"
    target = lib_root / "site-packages"
    target.mkdir(parents=True)
    assert module._find_site_packages_dir(tmp_path) == target


def test_ensure_repo_on_sys_path_writes_pth(tmp_path):
    module = _load_helper()
    venv = tmp_path / ".venv"
    site = venv / "Lib" / "site-packages"
    site.mkdir(parents=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    module.ensure_repo_on_sys_path(venv, repo)
    pth = site / "omniflowcentralrepo.pth"
    assert pth.exists()
    assert pth.read_text().strip() == str(repo)
