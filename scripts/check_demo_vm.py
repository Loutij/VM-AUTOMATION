#!/usr/bin/env python3
"""
Script pour vérifier l'état du déploiement DEMO_VM.
"""

import asyncio
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.common.database import db_session
from src.domain.models import Deployment, DeploymentLog, VirtualMachine


async def check_demo_vm():
    """Vérifie l'état du déploiement DEMO_VM."""
    async with db_session() as session:
        # Chercher le déploiement par nom de VM
        result = await session.execute(
            select(Deployment)
            .where(Deployment.vm_name == "DEMO_VM")
            .order_by(Deployment.created_at.desc())
        )
        deployments = result.scalars().all()
        
        if not deployments:
            print("❌ Aucun déploiement trouvé avec le nom 'DEMO_VM'")
            return
        
        print(f"✅ Trouvé {len(deployments)} déploiement(s) pour DEMO_VM\n")
        
        for idx, deployment in enumerate(deployments, 1):
            print(f"{'='*80}")
            print(f"DÉPLOIEMENT #{idx}")
            print(f"{'='*80}")
            print(f"ID: {deployment.id}")
            print(f"VM Name: {deployment.vm_name}")
            print(f"Status: {deployment.status.value}")
            print(f"Current Step: {deployment.current_step or 'N/A'}")
            print(f"Progress: {deployment.progress}%")
            print(f"Error Message: {deployment.error_message or 'Aucune erreur'}")
            print(f"Created At: {deployment.created_at}")
            print(f"Started At: {deployment.started_at or 'Pas encore démarré'}")
            print(f"Completed At: {deployment.completed_at or 'En cours ou non terminé'}")
            print(f"VM ID: {deployment.vm_id or 'Pas encore créée'}")
            print(f"Hypervisor ID: {deployment.hypervisor_id}")
            print(f"OS Template ID: {deployment.os_template_id}")
            
            # Récupérer la VM si elle existe
            if deployment.vm_id:
                vm_result = await session.execute(
                    select(VirtualMachine).where(VirtualMachine.id == deployment.vm_id)
                )
                vm = vm_result.scalar_one_or_none()
                if vm:
                    print(f"\n--- VM Details ---")
                    print(f"VM Name: {vm.name}")
                    print(f"VM State: {vm.state.value if vm.state else 'N/A'}")
                    print(f"Hypervisor VM ID: {vm.hypervisor_vm_id or 'N/A'}")
                    print(f"Status: {vm.status.value if vm.status else 'N/A'}")
            
            # Récupérer les logs
            logs_result = await session.execute(
                select(DeploymentLog)
                .where(DeploymentLog.deployment_id == deployment.id)
                .order_by(DeploymentLog.created_at)
            )
            logs = logs_result.scalars().all()
            
            print(f"\n--- Logs ({len(logs)} entrées) ---")
            if logs:
                for log in logs[-30:]:  # Derniers 30 logs
                    timestamp = log.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    level_icon = {
                        "info": "ℹ️",
                        "warning": "⚠️",
                        "error": "❌",
                        "debug": "🔍"
                    }.get(log.level.value, "•")
                    print(f"[{timestamp}] {level_icon} [{log.step}] {log.message}")
                    if log.details:
                        print(f"    Details: {json.dumps(log.details, indent=2, ensure_ascii=False)}")
            else:
                print("Aucun log disponible")
            
            print()


if __name__ == "__main__":
    asyncio.run(check_demo_vm())
