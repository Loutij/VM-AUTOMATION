#!/usr/bin/env python3
"""
Script de monitoring pour le déploiement DEMO_VM.
Surveille l'évolution sans intervenir.
"""

import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from src.common.database import db_session
from src.domain.models import Deployment, DeploymentLog, VirtualMachine


async def monitor_deployment():
    """Surveille le déploiement DEMO_VM."""
    print("🔍 Monitoring du déploiement DEMO_VM...")
    print("=" * 80)
    
    last_log_count = 0
    last_step = None
    
    while True:
        async with db_session() as session:
            # Chercher le déploiement
            result = await session.execute(
                select(Deployment)
                .where(Deployment.vm_name == "DEMO_VM")
                .order_by(Deployment.created_at.desc())
            )
            deployment = result.scalar_one_or_none()
            
            if not deployment:
                print("❌ Déploiement DEMO_VM non trouvé")
                await asyncio.sleep(10)
                continue
            
            # Récupérer les logs
            logs_result = await session.execute(
                select(DeploymentLog)
                .where(DeploymentLog.deployment_id == deployment.id)
                .order_by(DeploymentLog.created_at)
            )
            logs = logs_result.scalars().all()
            
            # Afficher les nouvelles informations
            current_time = datetime.now(timezone.utc)
            elapsed = (current_time - deployment.started_at).total_seconds() if deployment.started_at else 0
            elapsed_min = int(elapsed // 60)
            elapsed_sec = int(elapsed % 60)
            
            # Vérifier si le statut ou l'étape a changé
            status_changed = False
            if last_step != deployment.current_step:
                status_changed = True
                last_step = deployment.current_step
            
            # Afficher le statut
            print(f"\n[{current_time.strftime('%H:%M:%S')}] ⏱️  Temps écoulé: {elapsed_min}m {elapsed_sec}s")
            print(f"📊 Status: {deployment.status.value.upper()}")
            print(f"📍 Étape: {deployment.current_step or 'N/A'}")
            print(f"📈 Progression: {deployment.progress}%")
            
            if deployment.error_message:
                print(f"⚠️  Erreur: {deployment.error_message}")
            
            # Afficher les nouveaux logs
            if len(logs) > last_log_count:
                new_logs = logs[last_log_count:]
                print(f"\n📝 Nouveaux logs ({len(new_logs)}):")
                for log in new_logs:
                    timestamp = log.created_at.strftime("%H:%M:%S")
                    level_icon = {
                        "info": "ℹ️",
                        "warning": "⚠️",
                        "error": "❌",
                        "debug": "🔍"
                    }.get(log.level.value, "•")
                    print(f"   [{timestamp}] {level_icon} [{log.step}] {log.message}")
                    if log.details and log.details != {}:
                        print(f"      Details: {json.dumps(log.details, ensure_ascii=False)}")
                last_log_count = len(logs)
            
            # Récupérer les infos de la VM si elle existe
            if deployment.vm_id:
                vm_result = await session.execute(
                    select(VirtualMachine).where(VirtualMachine.id == deployment.vm_id)
                )
                vm = vm_result.scalar_one_or_none()
                if vm:
                    print(f"\n🖥️  VM: {vm.name}")
                    print(f"   État: {vm.state.value if vm.state else 'N/A'}")
                    print(f"   Status: {vm.status.value if vm.status else 'N/A'}")
            
            # Vérifier si terminé ou échoué
            if deployment.status.value in ("completed", "failed", "cancelled"):
                print("\n" + "=" * 80)
                if deployment.status.value == "completed":
                    print("✅ DÉPLOIEMENT TERMINÉ AVEC SUCCÈS!")
                elif deployment.status.value == "failed":
                    print("❌ DÉPLOIEMENT ÉCHOUÉ")
                    if deployment.error_message:
                        print(f"   Raison: {deployment.error_message}")
                else:
                    print("⏹️  DÉPLOIEMENT ANNULÉ")
                print("=" * 80)
                break
            
            print("-" * 80)
        
        # Attendre avant la prochaine vérification
        await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(monitor_deployment())
    except KeyboardInterrupt:
        print("\n\n⏹️  Monitoring arrêté par l'utilisateur")
