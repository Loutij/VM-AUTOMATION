#!/usr/bin/env python3
"""
Script pour relancer le déploiement DEMO_VM avec le correctif.
"""

import asyncio
from uuid import UUID

from src.common.database import db_session
from src.domain.deployment_service import DeploymentService
from src.domain.models import Deployment, DeploymentStatus


async def retry_deployment():
    """Relance le déploiement DEMO_VM."""
    async with db_session() as session:
        from sqlalchemy import select
        
        # Trouver le déploiement
        result = await session.execute(
            select(Deployment)
            .where(Deployment.vm_name == "DEMO_VM")
            .order_by(Deployment.created_at.desc())
        )
        deployment = result.scalar_one_or_none()
        
        if not deployment:
            print("❌ Déploiement DEMO_VM non trouvé")
            return
        
        print(f"✅ Déploiement trouvé: {deployment.id}")
        print(f"   Status actuel: {deployment.status.value}")
        print(f"   Current Step: {deployment.current_step}")
        print(f"   VM ID: {deployment.vm_id}\n")
        
        # Vérifier si on peut relancer
        if deployment.status == DeploymentStatus.COMPLETED:
            print("⚠️  Le déploiement est déjà terminé")
            return
        
        if deployment.status == DeploymentStatus.CANCELLED:
            print("⚠️  Le déploiement a été annulé")
            return
        
        # Si le déploiement est bloqué en in_progress, on peut le relancer
        if deployment.status == DeploymentStatus.IN_PROGRESS:
            print("⚠️  Le déploiement est en cours mais semble bloqué")
            print("   On va le relancer depuis le début avec le nouveau code...\n")
        
        # Relancer le déploiement
        service = DeploymentService(session)
        print("🔄 Relance du déploiement avec le correctif PowerShell Direct...")
        
        try:
            # start_deployment va gérer le retry automatiquement
            # Si deployment.vm_id existe, il va nettoyer et recréer la VM
            await service.start_deployment(deployment.id)
            await session.commit()
            
            print("✅ Déploiement relancé avec succès!")
            print("   Le correctif PowerShell Direct (utilisation du nom de la VM) sera appliqué")
            print("   Le déploiement devrait maintenant progresser au-delà de 'waiting_vm_ready'")
            
        except Exception as e:
            print(f"❌ Erreur lors du relancement: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(retry_deployment())
