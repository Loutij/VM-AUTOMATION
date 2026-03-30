"""
Création locale d'images ISO et floppy pour les déploiements ESXi.

Remplace les opérations oscdimg/PowerShell utilisées pour Hyper-V.
Utilise genisoimage/xorriso (subprocess) ou pycdlib (pure Python fallback).
"""

import os
import struct
import subprocess
import tempfile
import time
from pathlib import Path

from src.common.logging import get_logger

logger = get_logger(__name__)


def create_seed_iso(seed_content: str, config_type: str, output_path: str) -> None:
    """
    Crée une seed ISO contenant la configuration d'installation.

    Args:
        seed_content: Contenu de la config (preseed.cfg, ks.cfg, user-data, etc.)
        config_type: Type de config (preseed, kickstart, autoinstall, cloud-init)
        output_path: Chemin de sortie de l'ISO
    """
    with tempfile.TemporaryDirectory(prefix="vm-auto-seed-") as tmpdir:
        # Créer la structure de fichiers selon le type
        if config_type == "preseed":
            # Debian preseed: preseed.cfg à la racine
            seed_file = os.path.join(tmpdir, "preseed.cfg")
            with open(seed_file, "w", encoding="utf-8") as f:
                f.write(seed_content)
            volume_id = "PRESEED"

        elif config_type == "kickstart":
            # RHEL/Rocky kickstart: ks.cfg à la racine
            seed_file = os.path.join(tmpdir, "ks.cfg")
            with open(seed_file, "w", encoding="utf-8") as f:
                f.write(seed_content)
            volume_id = "OEMDRV"  # RHEL auto-detects OEMDRV label

        elif config_type in ("autoinstall", "cloud-init"):
            # Ubuntu autoinstall / cloud-init NoCloud
            # Structure: /meta-data + /user-data (+ /network-config optionnel)
            meta_data = os.path.join(tmpdir, "meta-data")
            user_data = os.path.join(tmpdir, "user-data")

            with open(meta_data, "w", encoding="utf-8") as f:
                f.write("")  # meta-data peut être vide
            with open(user_data, "w", encoding="utf-8") as f:
                f.write(seed_content)
            volume_id = "cidata"  # cloud-init NoCloud standard label

        else:
            # Generic: write content as seed.cfg
            seed_file = os.path.join(tmpdir, "seed.cfg")
            with open(seed_file, "w", encoding="utf-8") as f:
                f.write(seed_content)
            volume_id = "SEED"

        # Try system tools first, then pure Python fallback
        if _try_genisoimage(tmpdir, output_path, volume_id):
            return
        if _try_xorriso(tmpdir, output_path, volume_id):
            return
        if _try_mkisofs(tmpdir, output_path, volume_id):
            return

        # Pure Python fallback using pycdlib
        _create_iso_pycdlib(tmpdir, output_path, volume_id)


def _try_genisoimage(source_dir: str, output: str, volume_id: str) -> bool:
    """Essaie de créer l'ISO avec genisoimage."""
    try:
        result = subprocess.run(
            ["genisoimage", "-o", output, "-V", volume_id, "-r", "-J", source_dir],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            logger.info("seed_iso_created", tool="genisoimage", path=output)
            return True
        logger.warning("genisoimage_failed", stderr=result.stderr[:200])
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("genisoimage_error", error=str(e))
    return False


def _try_xorriso(source_dir: str, output: str, volume_id: str) -> bool:
    """Essaie de créer l'ISO avec xorriso."""
    try:
        result = subprocess.run(
            [
                "xorriso",
                "-as",
                "mkisofs",
                "-o",
                output,
                "-V",
                volume_id,
                "-r",
                "-J",
                source_dir,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            logger.info("seed_iso_created", tool="xorriso", path=output)
            return True
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("xorriso_error", error=str(e))
    return False


def _try_mkisofs(source_dir: str, output: str, volume_id: str) -> bool:
    """Essaie de créer l'ISO avec mkisofs."""
    try:
        result = subprocess.run(
            ["mkisofs", "-o", output, "-V", volume_id, "-r", "-J", source_dir],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            logger.info("seed_iso_created", tool="mkisofs", path=output)
            return True
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("mkisofs_error", error=str(e))
    return False


def _create_iso_pycdlib(source_dir: str, output: str, volume_id: str) -> None:
    """Crée l'ISO en pure Python avec pycdlib."""
    try:
        import pycdlib
    except ImportError:
        raise RuntimeError(
            "Aucun outil ISO disponible. Installez genisoimage, xorriso, ou pycdlib:\n"
            "  apt install genisoimage  # ou\n"
            "  pip install pycdlib"
        )

    iso = pycdlib.PyCdlib()
    iso.new(vol_ident=volume_id, joliet=3, rock_ridge="1.09")

    for root, _dirs, files in os.walk(source_dir):
        rel_root = os.path.relpath(root, source_dir)

        if rel_root != ".":
            iso_dir = "/" + rel_root.replace(os.sep, "/").upper()
            joliet_dir = "/" + rel_root.replace(os.sep, "/")
            rr_name = os.path.basename(rel_root)
            iso.add_directory(iso_dir, joliet_path=joliet_dir, rr_name=rr_name)

        for filename in files:
            filepath = os.path.join(root, filename)

            # ISO9660 name (uppercase, 8.3 compatible)
            if "." in filename:
                base, ext = filename.rsplit(".", 1)
                iso_name = base.upper()[:8] + "." + ext.upper()[:3] + ";1"
            else:
                iso_name = filename.upper()[:8] + ".;1"

            if rel_root == ".":
                iso_path = "/" + iso_name
                joliet_path = "/" + filename
            else:
                iso_path = (
                    "/" + rel_root.replace(os.sep, "/").upper() + "/" + iso_name
                )
                joliet_path = (
                    "/" + rel_root.replace(os.sep, "/") + "/" + filename
                )

            iso.add_file(
                filepath,
                iso_path=iso_path,
                joliet_path=joliet_path,
                rr_name=filename,
            )

    iso.write(output)
    iso.close()
    logger.info("seed_iso_created", tool="pycdlib", path=output)


def create_floppy_image(unattend_content: str, output_path: str) -> None:
    """
    Crée une image floppy 1.44 Mo (FAT12) contenant Autounattend.xml.

    Windows cherche automatiquement Autounattend.xml sur les lecteurs
    disponibles lors de l'installation.

    Pure Python implementation — no external tools needed.
    """
    FLOPPY_SIZE = 1474560  # 1.44 MB
    SECTOR_SIZE = 512
    SECTORS_PER_CLUSTER = 1
    RESERVED_SECTORS = 1
    NUM_FATS = 2
    ROOT_DIR_ENTRIES = 224
    TOTAL_SECTORS = FLOPPY_SIZE // SECTOR_SIZE
    SECTORS_PER_FAT = 9
    SECTORS_PER_TRACK = 18
    NUM_HEADS = 2

    # Initialize floppy image
    image = bytearray(FLOPPY_SIZE)

    # --- Boot Sector (Sector 0) ---
    # Jump + NOP
    image[0:3] = b"\xEB\x3C\x90"
    # OEM Name
    image[3:11] = b"MSDOS5.0"
    # Bytes per sector
    struct.pack_into("<H", image, 11, SECTOR_SIZE)
    # Sectors per cluster
    image[13] = SECTORS_PER_CLUSTER
    # Reserved sectors
    struct.pack_into("<H", image, 14, RESERVED_SECTORS)
    # Number of FATs
    image[16] = NUM_FATS
    # Root dir entries
    struct.pack_into("<H", image, 17, ROOT_DIR_ENTRIES)
    # Total sectors (16-bit)
    struct.pack_into("<H", image, 19, TOTAL_SECTORS)
    # Media descriptor (F0 = 3.5" floppy)
    image[21] = 0xF0
    # Sectors per FAT
    struct.pack_into("<H", image, 22, SECTORS_PER_FAT)
    # Sectors per track
    struct.pack_into("<H", image, 24, SECTORS_PER_TRACK)
    # Number of heads
    struct.pack_into("<H", image, 26, NUM_HEADS)
    # Boot signature
    image[38] = 0x29
    # Volume serial number
    serial = int(time.time()) & 0xFFFFFFFF
    struct.pack_into("<I", image, 39, serial)
    # Volume label
    image[43:54] = b"OEMFLOPPY  "
    # FS type
    image[54:62] = b"FAT12   "
    # Boot sector signature
    image[510] = 0x55
    image[511] = 0xAA

    # --- FAT tables ---
    fat_start = RESERVED_SECTORS * SECTOR_SIZE
    # FAT media byte + 0xFF 0xFF
    for i in range(NUM_FATS):
        offset = fat_start + i * SECTORS_PER_FAT * SECTOR_SIZE
        image[offset] = 0xF0
        image[offset + 1] = 0xFF
        image[offset + 2] = 0xFF

    # --- Root Directory ---
    root_dir_start = (RESERVED_SECTORS + NUM_FATS * SECTORS_PER_FAT) * SECTOR_SIZE
    data_start = root_dir_start + ROOT_DIR_ENTRIES * 32

    # Write Autounattend.xml
    file_content = unattend_content.encode("utf-8")
    file_size = len(file_content)

    if file_size > FLOPPY_SIZE - data_start:
        raise ValueError(
            f"Le fichier unattend est trop grand ({file_size} octets) "
            f"pour une floppy 1.44 Mo"
        )

    # Volume label entry
    image[root_dir_start : root_dir_start + 11] = b"OEMFLOPPY  "
    image[root_dir_start + 11] = 0x08  # Volume label attribute

    # File directory entry (Autounattend.xml -> 8.3: AUTOUNAT.XML)
    entry_offset = root_dir_start + 32  # Second entry
    # Filename (8.3 format)
    image[entry_offset : entry_offset + 8] = b"AUTOUNAT"
    image[entry_offset + 8 : entry_offset + 11] = b"XML"
    # Attributes (normal file)
    image[entry_offset + 11] = 0x20
    # First cluster (cluster 2 = first data cluster)
    struct.pack_into("<H", image, entry_offset + 26, 2)
    # File size
    struct.pack_into("<I", image, entry_offset + 28, file_size)

    # Write file data starting at cluster 2
    image[data_start : data_start + file_size] = file_content

    # Update FAT chains
    clusters_needed = (file_size + SECTOR_SIZE - 1) // SECTOR_SIZE
    for i in range(NUM_FATS):
        fat_offset = fat_start + i * SECTORS_PER_FAT * SECTOR_SIZE
        for cluster in range(2, 2 + clusters_needed):
            if cluster == 2 + clusters_needed - 1:
                # Last cluster: EOF marker
                _write_fat12(image, fat_offset, cluster, 0xFFF)
            else:
                _write_fat12(image, fat_offset, cluster, cluster + 1)

    # Ensure parent directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "wb") as f:
        f.write(image)

    logger.info("floppy_image_created", path=output_path, file_size=file_size)


def _write_fat12(image: bytearray, fat_offset: int, cluster: int, value: int) -> None:
    """Écrit une entrée FAT12 (12 bits par cluster)."""
    byte_offset = fat_offset + (cluster * 3) // 2
    if cluster % 2 == 0:
        image[byte_offset] = value & 0xFF
        image[byte_offset + 1] = (image[byte_offset + 1] & 0xF0) | (
            (value >> 8) & 0x0F
        )
    else:
        image[byte_offset] = (image[byte_offset] & 0x0F) | ((value << 4) & 0xF0)
        image[byte_offset + 1] = (value >> 4) & 0xFF


if __name__ == "__main__":
    import sys

    test_dir = tempfile.mkdtemp(prefix="vm-auto-seed-test-")
    print(f"Test output directory: {test_dir}")

    # --- Test 1: Preseed ISO ---
    print("\n[Test 1] Creating preseed seed ISO...")
    preseed_iso = os.path.join(test_dir, "preseed-test.iso")
    create_seed_iso(
        seed_content="d-i debian-installer/locale string en_US\n",
        config_type="preseed",
        output_path=preseed_iso,
    )
    size = os.path.getsize(preseed_iso)
    print(f"  OK: {preseed_iso} ({size} bytes)")

    # --- Test 2: Kickstart ISO ---
    print("\n[Test 2] Creating kickstart seed ISO...")
    ks_iso = os.path.join(test_dir, "kickstart-test.iso")
    create_seed_iso(
        seed_content="install\ntext\nlang en_US.UTF-8\n",
        config_type="kickstart",
        output_path=ks_iso,
    )
    size = os.path.getsize(ks_iso)
    print(f"  OK: {ks_iso} ({size} bytes)")

    # --- Test 3: Cloud-init ISO ---
    print("\n[Test 3] Creating cloud-init seed ISO...")
    ci_iso = os.path.join(test_dir, "cloud-init-test.iso")
    create_seed_iso(
        seed_content="#cloud-config\nusers:\n  - name: test\n",
        config_type="cloud-init",
        output_path=ci_iso,
    )
    size = os.path.getsize(ci_iso)
    print(f"  OK: {ci_iso} ({size} bytes)")

    # --- Test 4: Floppy image ---
    print("\n[Test 4] Creating floppy image...")
    floppy_path = os.path.join(test_dir, "autounattend.flp")
    create_floppy_image(
        unattend_content='<?xml version="1.0" encoding="utf-8"?>\n<unattend>\n  <test>hello</test>\n</unattend>\n',
        output_path=floppy_path,
    )
    size = os.path.getsize(floppy_path)
    print(f"  OK: {floppy_path} ({size} bytes)")
    assert size == 1474560, f"Expected 1474560 bytes, got {size}"

    # --- Test 5: Verify ISO contents with isoinfo ---
    print("\n[Test 5] Verifying preseed ISO contents...")
    try:
        result = subprocess.run(
            ["isoinfo", "-J", "-l", "-i", preseed_iso],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            print(f"  ISO contents:\n{result.stdout}")
        else:
            print(f"  isoinfo not available or failed: {result.stderr[:100]}")
    except FileNotFoundError:
        print("  isoinfo not installed, skipping content verification")

    print(f"\nAll tests passed! Output files in: {test_dir}")
    print("Clean up with: rm -rf", test_dir)
    sys.exit(0)
