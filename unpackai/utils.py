# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/10_utils.ipynb (unless otherwise specified).

__all__ = ['PathStr', 'PathURL', 'is_jupyter', 'IS_JUPYTER', 'check_img', 'clean_error_img', 'hush', 'static_root',
           'STATIC', 'friendly_size', 'ls', 'gv', 'get_url_size', 'download', 'url_2_text', 'download_and_unpack',
           'unpack_archive', 'read_csv_from_zip']

# Cell
import logging
import requests
import shutil
import tarfile
import tempfile
from datetime import datetime
from mimetypes import types_map
from pathlib import Path
from typing import Callable, List, Union
from zipfile import ZipFile

import graphviz
import pandas as pd
from bs4 import BeautifulSoup
from IPython.core import magic
from IPython.display import Javascript
from ipywidgets import Output, VBox, Button, HTML
from PIL import Image
from tqdm.notebook import tqdm
from uuid import uuid4


PathStr = Union[Path, str]
PathURL = Union[Path, str]


# Cell
def is_jupyter():
    try:
        ishell = get_ipython()
        shell = ishell.__class__.__name__
        if shell == 'ZMQInteractiveShell':
            return True   # Jupyter notebook or qtconsole
        elif shell == 'TerminalInteractiveShell':
            return False  # Terminal running IPython
        elif "google.colab._shell.Shell" in str(ishell):
            return True # Colab compatibility
        else:
            return False  # Other type (?)
    except NameError:
        return False  # Probably standard Python interpreter

IS_JUPYTER = is_jupyter()

# Internal Cell
logger = logging.getLogger("unpackai.utils")

# Cell
def check_img(
    img: Path,
    formats: List[str] = [".jpg", ".jpeg", ".png", ".bmp"],
) -> None:
    """
    Check on a single image,
    If it's quality is troublesome
        we unlink/ditch the image
    """
    img = Path(img)
    # check if this path is an image
    if img.suffix.lower().split("?")[0] not in formats:
        return

    try:
        # try to open that image and then (to check truncated image)
        # We need to include in a with block to close the image before deleting
        with Image.open(img) as im:
            im.load()
    except Exception:
        if img.exists():
            img.unlink()
            logging.warning(f"Removed erroneous img: {img}")
            return


def clean_error_img(
    path: Path,
    progress: bool = True,
) -> None:
    """
    - path: an image directory
    - progress: do we print out progress bar or not
        default True
    """
    path = Path(path)

    # check directory existence
    if path.exists() == False:
        raise FileExistsError(
            f"""path does not exists on:{path},
    make sure there is a directory "{path.name}".
    under directory "{path.parent}"
    """)

    # create iterator, probably with progress bar
    iterator = tqdm(list(path.iterdir()), leave=False)\
        if progress else path.iterdir()

    for obj in iterator:
        if obj.is_dir():
            # use recursion to clean the sub folder
            clean_error_img(obj, progress=progress)
        else:
            # cheking on a single image
            check_img(obj)

# Cell
def hush(line, cell):
    """
    A magic cell function to collapse the print out
    %%hush
    how_loud = 100
    how_verbose = "very"
    do_some_python_thing(how_loud, how_verbose)
    """
    # the current output widget
    out = Output()
    output_box = VBox([out])

    # create uuid for DOM identifying
    uuid = str(uuid4())

    # default setting is to hide the print out
    output_box.layout.display = "none"
    # the toggling button
    show_btn = Button(description="toggle output")
    show_btn.add_class(f"hush_toggle_{uuid}")
    output_box.add_class(f"hush_output_{uuid}")


    # A control panel containing a button
    # and the output box
    total_control = VBox([show_btn, output_box])
    display(total_control)

    # assign JS listener
    display(Javascript(f"""
    console.info("loading toggle event: {uuid}")
    const toggle_hush = (e) =>\u007b
        var op = document.querySelector(".hush_output_{uuid}");
        if(op.style.display=="none")\u007b
             op.style.display="block"

        \u007d else \u007b
            op.style.display="none"
        \u007d

    \u007d
    document.querySelector('.hush_toggle_{uuid}').onclick=toggle_hush
    """))

    with out:
        ishell = get_ipython()
        # excute the code in cell
        result = ishell.run_cell(
            cell, silent=False)

    # we still want the error to be proclaimed loudly
    if result.error_in_exec:
        logging.error(f"'{result.error_in_exec}' happened, breaking silence now")
        result.raise_error()

if IS_JUPYTER:
    magic.register_cell_magic(hush)

# Cell
def static_root() -> Path:
    """
    Return static path
    """
    import unpackai

    unpackai_path = Path(unpackai.__path__[0])
    if not unpackai_path.exists():
        egg_path = Path(f"{unpackai_path}.egg-link")
        unpackai_path = Path(egg_path.read_text())

    return unpackai_path / "static"


STATIC = static_root()

# Internal Cell
def _iter_files(root: Path, exclude_dir: List[str], hide_info: bool):
    """Return all info of files found in a root directory"""
    for f in root.rglob("*"):
        if any(d in f.parts for d in exclude_dir):
            continue

        info = {
            "Name": f.name,
            "Parent": f.parent.name,
            "Path": f.as_posix(),
            "Level": len(f.relative_to(root).parent.parts),
            "Last_Modif": datetime.fromtimestamp(f.stat().st_mtime),
        }
        if f.is_file():
            info.update(
                {
                    "FileDir": "File",
                    "Extension": f.suffix or f.name,
                    "Type": types_map.get(f.suffix.lower()),
                }
            )
            if not hide_info:
                size = f.stat().st_size
                info.update(
                    {
                        "Size": size,
                        "Friendly_Size": friendly_size(size),
                    }
                )
        elif f.is_dir():
            info.update({"FileDir": "Dir"})

        yield info


# Cell
def friendly_size(size: float) -> str:
    """Convert a size in bytes (as float) to a size with unit (as a string)"""
    unit = "B"
    # Reminder: 1 KB = 1024 B, and 1 MB = 1024 KB, ...
    for letter in "KMG":
        if size >= 1024:
            size /= 1024
            unit = f"{letter}B"

    # We want to keep 2 digits after floating point
    # because it is a good balance between precision and concision
    return f"{size:0.2f} {unit}"


def ls(root: PathStr, exclude: List[str] = None, hide_info=False) -> pd.DataFrame:
    """Return a DataFrame with list of files & directories in a given path.

    Args:
        root: root path to look for files and directories recursively
        exclude: optional list of names to exclude in the search (e.g. `[".git"]`)
    """
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"Path {root} does not exist or is not a directory")
    df = pd.DataFrame(
        _iter_files(root, exclude_dir=exclude or [], hide_info=hide_info)
    )
    return df.sort_values(by=["Path"])


# Cell
def gv(source: str, rankdir="LR"):
    """Generate a GraphViz diagram, with a settable orientation (i.e. rankdir)"""
    source = source.strip().rstrip(";")
    return graphviz.Source(f'digraph G {{  rankdir="{rankdir}" {source}; }}')


# Cell
def get_url_size(url: str) -> int:
    """Returns the size of URL, or -1 if it cannot get it"""
    with requests.request("HEAD", url) as resp:
        if resp.status_code != 200:
            raise ConnectionError(f"Error when retrieving size from {url}")

        return int(resp.headers.get("Content-Length", -1))


# Cell
def download(url: str, dest: PathStr = None) -> Path:
    """Download file and return the Path of the downloaded file

    If the destination is not specified, download in the current directory
    with the name specified in the URL
    """
    # We can allow empty destination, in which case we use file name in URL
    # We need to ensure that destination is a Path
    dest = Path(dest or url.rpartition("/")[-1])

    # For big files, we will split into chunks
    # We might also consider adding a progress bar
    size = get_url_size(url)
    if size < 1024 * 1024:
        with requests.get(url) as resp:
            resp.raise_for_status()
            dest.write_bytes(resp.content)

    else:
        with requests.get(url, stream=True) as resp:
            resp.raise_for_status()
            with dest.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

    logger.info(f"Downloaded {url} to {dest}")
    return dest


def url_2_text(url: str) -> str:
    """Extract text content from an URL (textual content for an HTML)"""
    resp = requests.get(url)
    if resp.status_code != 200:
        raise ConnectionError(f"Error when retrieving text content from {url}")

    resp.encoding = "utf-8"
    content_type = resp.headers["Content-Type"]
    if "html" in content_type:
        text = BeautifulSoup(resp.text).text
    else:
        text = resp.text
    return text


# Cell

# We will re-use directly the unzip function from shutil
# Since we want it in our "all", we just assign to itself so nbdev can detect it
unpack_archive = shutil.unpack_archive

# Equivalent to:
# def unpack_archive(filename, extract_dir=None, format=None):
#     return shutil.unpack_archive(filename, extract_dir=None, format=None)


def download_and_unpack(url: str, extract_dir: PathStr = None, fmt: str = None) -> Path:
    """Download a file and unzip it. Returns the path of unzipped directory

    Args:
        url: URL of the archive to download
        extract_dir: name of the target directory, where the archive is unpacked.
                    If not provided, <working directory> / <archive name without extesion> is used.
        fmt: archive format (one of "zip", "tar", "gztar", "bztar",or "xztar").
                Or any other registered format. If not provided, it is guessed from extension.
    """
    # We will store the downloaded archive in a temporary folder
    with tempfile.TemporaryDirectory() as tmpdirname:
        dest = Path(tmpdirname) / url.split("?")[0].rpartition("/")[-1]
        download(url, dest=dest)

        if extract_dir is None:
            extract_dir = Path.cwd() / dest.stem

        unpack_archive(str(dest), extract_dir=str(extract_dir), format=fmt)
        logger.info(f"Extracted {url} to folder {dest}")

    return Path(extract_dir)


# Internal Cell
def _zip_csv_2_df(zip_path:Path, csv_path:PathStr) -> pd.DataFrame:
    """CSV in zip to DataFrame"""
    with ZipFile(zip_path) as zf:
        try:
            with zf.open(str(csv_path)) as f_csv:
                return pd.read_csv(f_csv)
        except KeyError:
            files = "\n".join(f" * {f}" for f in zf.namelist() if f.lower().endswith(".csv"))
            raise FileNotFoundError(
                f'CSV file "{csv_path}" not found in "{zip_path}" '
                f"containing following CSV files:\n{files}"
            ) from None


def _tar_csv_2_df(tar_path:Path, csv_path:PathStr) -> pd.DataFrame:
    """CSV in tar to DataFrame"""
    with tarfile.open(tar_path) as tf:
        try:
            csv_member = tf.getmember(str(csv_path))
            return pd.read_csv(tf.extractfile(member=csv_member))
        except KeyError:
            files = "\n".join(f" * {f}" for f in tf.getnames() if f.lower().endswith(".csv"))
            raise FileNotFoundError(
                f'CSV file "{csv_path}" not found in "{tar_path}" '
                f"containing following CSV files:\n{files}"
            ) from None


# Cell
def read_csv_from_zip(archive: PathURL, csv_path: PathStr) -> pd.DataFrame:
    """Load a CSV file inside a zip/tar and returns the equivalent pandas `DataFrame`

    Args:
        archive: path or URL of the zip (or tar/tag.gz) file
        csv_path: path of csv relative to root of archive
            Note: if root is a folder, csv_path shall include this path (e.g. "archive/my_table.csv")
    """
    if Path(csv_path).suffix.lower() != ".csv":
        raise AttributeError(
            f'2nd argument ("csv_path") shall be a CSV file but is "{csv_path}"'
        )

    with tempfile.TemporaryDirectory() as tmpdirname:
        if isinstance(archive, str) and archive.startswith("http"):
            zip_path = Path(tmpdirname) / archive.split("?")[0].rpartition("/")[-1]
            download(archive, dest=zip_path)
        else:
            zip_path = Path(archive)

        extensions = "".join(zip_path.suffixes[-2:]).lower()
        if extensions == ".zip":
            return _zip_csv_2_df(zip_path, csv_path)
        elif extensions in (".tar", ".tar.gz"):
            return _tar_csv_2_df(zip_path, csv_path)
        else:
            raise AttributeError(
                f'Archive shall be either .zip, .tar, or .tar.gz but is "{zip_path}"'
            )

# Cell
try:
    ishell = get_ipython()
except NameError as e:
    from IPython.testing.globalipapp import get_ipython, start_ipython
    ishell = start_ipython()
    print(get_ipython())