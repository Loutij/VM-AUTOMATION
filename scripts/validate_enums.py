#!/usr/bin/env python3
"""
Script de validation pour vérifier la cohérence des enums entre:
- Les migrations Alembic
- Les modèles SQLAlchemy
- Les types TypeScript frontend

Usage:
    python scripts/validate_enums.py
"""

import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent


def extract_python_enum_values(file_path: Path, enum_name: str) -> set[str]:
    """Extrait les valeurs d'un enum Python."""
    content = file_path.read_text()
    
    # Pattern pour trouver les valeurs de l'enum
    pattern = rf'class {enum_name}\(.*?\):\s*""".*?"""(.*?)(?=class |\Z)'
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        return set()
    
    enum_body = match.group(1)
    # Extraire les valeurs: NAME = "value"
    values = re.findall(r'\s+\w+\s*=\s*["\'](\w+)["\']', enum_body)
    return set(values)


def extract_migration_enum_values(file_path: Path, enum_name: str) -> set[str]:
    """Extrait les valeurs d'un enum dans une migration Alembic."""
    content = file_path.read_text()
    
    # Pattern pour sa.Enum(..., name='enumname')
    pattern = rf"sa\.Enum\((.*?),\s*name=['\"]?{enum_name}['\"]?\)"
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        # Essayer avec postgresql.ENUM
        pattern = rf"postgresql\.ENUM\((.*?),\s*name=['\"]?{enum_name}['\"]?\)"
        match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        return set()
    
    enum_args = match.group(1)
    values = re.findall(r"['\"](\w+)['\"]", enum_args)
    return set(values)


def extract_typescript_enum_values(file_path: Path, type_name: str) -> set[str]:
    """Extrait les valeurs d'un type TypeScript."""
    content = file_path.read_text()
    
    # Pattern pour type Name = 'value1' | 'value2' | ...
    pattern = rf"type {type_name}\s*=\s*(.*?);"
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        return set()
    
    type_def = match.group(1)
    values = re.findall(r"['\"](\w+)['\"]", type_def)
    return set(values)


def validate_vmstate():
    """Valide VMState entre migration et modèle."""
    print("\n=== Validation VMState ===")
    
    model_values = extract_python_enum_values(
        ROOT_DIR / "src/domain/models.py", "VMState"
    )
    migration_values = extract_migration_enum_values(
        ROOT_DIR / "alembic/versions/889a3e192265_add_state_column_to_vm.py", "vmstate"
    )
    frontend_values = extract_typescript_enum_values(
        ROOT_DIR / "frontend/src/types/index.ts", "VMState"
    )
    
    print(f"  Modèle Python: {sorted(model_values)}")
    print(f"  Migration: {sorted(migration_values)}")
    print(f"  Frontend: {sorted(frontend_values)}")
    
    if model_values == migration_values == frontend_values:
        print("  ✅ VMState: OK")
        return True
    else:
        print("  ❌ VMState: MISMATCH")
        if model_values != migration_values:
            print(f"    Diff modèle/migration: {model_values.symmetric_difference(migration_values)}")
        if model_values != frontend_values:
            print(f"    Diff modèle/frontend: {model_values.symmetric_difference(frontend_values)}")
        return False


def validate_deployment_status():
    """Valide DeploymentStatus entre migration et modèle."""
    print("\n=== Validation DeploymentStatus ===")
    
    model_values = extract_python_enum_values(
        ROOT_DIR / "src/domain/models.py", "DeploymentStatus"
    )
    migration_values = extract_migration_enum_values(
        ROOT_DIR / "alembic/versions/001_initial_schema.py", "deploymentstatus"
    )
    frontend_values = extract_typescript_enum_values(
        ROOT_DIR / "frontend/src/types/index.ts", "DeploymentStatus"
    )
    
    print(f"  Modèle Python: {sorted(model_values)}")
    print(f"  Migration: {sorted(migration_values)}")
    print(f"  Frontend: {sorted(frontend_values)}")
    
    if model_values == migration_values == frontend_values:
        print("  ✅ DeploymentStatus: OK")
        return True
    else:
        print("  ❌ DeploymentStatus: MISMATCH")
        return False


def validate_software_category():
    """Valide SoftwareCategory entre migration et modèle."""
    print("\n=== Validation SoftwareCategory ===")
    
    model_values = extract_python_enum_values(
        ROOT_DIR / "src/domain/models.py", "SoftwareCategory"
    )
    migration_values = extract_migration_enum_values(
        ROOT_DIR / "alembic/versions/003_software_marketplace.py", "softwarecategory"
    )
    frontend_values = extract_typescript_enum_values(
        ROOT_DIR / "frontend/src/types/index.ts", "SoftwareCategory"
    )
    
    print(f"  Modèle Python: {sorted(model_values)}")
    print(f"  Migration: {sorted(migration_values)}")
    print(f"  Frontend: {sorted(frontend_values)}")
    
    if model_values == migration_values == frontend_values:
        print("  ✅ SoftwareCategory: OK")
        return True
    else:
        print("  ❌ SoftwareCategory: MISMATCH")
        return False


def validate_category_info():
    """Valide que CATEGORY_INFO contient toutes les catégories de l'enum."""
    print("\n=== Validation CATEGORY_INFO ===")
    
    model_values = extract_python_enum_values(
        ROOT_DIR / "src/domain/models.py", "SoftwareCategory"
    )
    
    # Extraire les clés de CATEGORY_INFO
    catalog_content = (ROOT_DIR / "src/domain/software_catalog.py").read_text()
    pattern = r'CATEGORY_INFO.*?=\s*\{(.*?)\n\}'
    match = re.search(pattern, catalog_content, re.DOTALL)
    
    if not match:
        print("  ❌ CATEGORY_INFO non trouvé")
        return False
    
    category_info_keys = set(re.findall(r'"(\w+)":\s*\{', match.group(1)))
    
    print(f"  Enum SoftwareCategory: {sorted(model_values)}")
    print(f"  CATEGORY_INFO keys: {sorted(category_info_keys)}")
    
    if model_values == category_info_keys:
        print("  ✅ CATEGORY_INFO: OK")
        return True
    else:
        missing = model_values - category_info_keys
        extra = category_info_keys - model_values
        if missing:
            print(f"  ❌ Manquant dans CATEGORY_INFO: {missing}")
        if extra:
            print(f"  ⚠️ Extra dans CATEGORY_INFO: {extra}")
        return False


def main():
    """Point d'entrée principal."""
    print("=" * 60)
    print("Validation de cohérence des enums")
    print("=" * 60)
    
    results = [
        validate_vmstate(),
        validate_deployment_status(),
        validate_software_category(),
        validate_category_info(),
    ]
    
    print("\n" + "=" * 60)
    if all(results):
        print("✅ Toutes les validations passent!")
        return 0
    else:
        print("❌ Certaines validations ont échoué")
        return 1


if __name__ == "__main__":
    sys.exit(main())
