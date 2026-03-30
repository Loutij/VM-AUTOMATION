import { useState, useEffect } from 'react';
import {
  Users,
  UserPlus,
  Shield,
  ShieldCheck,
  Pencil,
  Trash2,
  KeyRound,
  UserX,
  UserCheck,
  Search,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock,
  Rocket,
  ScrollText,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { Button, Input, Select, Modal, ConfirmModal } from '../components/ui';
import { Header } from '../components/layout';
import { adminApi, deploymentsApi } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import type { AdminUser, UserRole, Deployment, AuditLogEntry } from '../types';

// =============================================================================
// Composant principal
// =============================================================================

export function AdminUsers() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  // Modals
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editUser, setEditUser] = useState<AdminUser | null>(null);
  const [resetPasswordUser, setResetPasswordUser] = useState<AdminUser | null>(null);
  const [deleteUser, setDeleteUser] = useState<AdminUser | null>(null);

  // Toast-like feedback
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const showFeedback = (type: 'success' | 'error', message: string) => {
    setFeedback({ type, message });
    setTimeout(() => setFeedback(null), 4000);
  };

  // Charger les utilisateurs
  const loadUsers = async () => {
    try {
      setLoading(true);
      const data = await adminApi.listUsers();
      setUsers(data);
      setError(null);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || 'Erreur lors du chargement des utilisateurs';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, []);

  // Filtrer
  const filteredUsers = users.filter(
    (u) =>
      u.username.toLowerCase().includes(search.toLowerCase()) ||
      u.email.toLowerCase().includes(search.toLowerCase()) ||
      (u.full_name && u.full_name.toLowerCase().includes(search.toLowerCase()))
  );

  // Vérifier accès admin
  if (currentUser?.role !== 'admin') {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center space-y-4">
          <AlertTriangle size={48} className="mx-auto text-yellow-500" />
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">Accès refusé</h2>
          <p className="text-gray-500 dark:text-dark-400">
            Vous devez avoir le rôle administrateur pour accéder à cette page.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-light-100 dark:bg-dark-900">
      <Header title="Administration" />

      <div className="p-4 sm:p-6 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-oto-500/10 dark:bg-oto-500/20 rounded-xl flex items-center justify-center">
            <Users size={22} className="text-oto-500" />
          </div>
          <div>
            <h1 className="text-2xl font-black uppercase tracking-tight text-gray-900 dark:text-white">
              Gestion des utilisateurs
            </h1>
            <p className="text-sm text-gray-500 dark:text-dark-400">
              {users.length} utilisateur{users.length > 1 ? 's' : ''} enregistré{users.length > 1 ? 's' : ''}
            </p>
          </div>
        </div>
        <Button leftIcon={<UserPlus size={18} />} onClick={() => setShowCreateModal(true)}>
          Nouvel utilisateur
        </Button>
      </div>

      {/* Feedback */}
      {feedback && (
        <div
          className={`px-4 py-3 rounded-lg border text-sm font-medium ${
            feedback.type === 'success'
              ? 'bg-green-50 dark:bg-green-500/10 text-green-700 dark:text-green-400 border-green-200 dark:border-green-500/20'
              : 'bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400 border-red-200 dark:border-red-500/20'
          }`}
        >
          {feedback.message}
        </div>
      )}

      {/* Barre de recherche */}
      <div className="max-w-md">
        <Input
          placeholder="Rechercher un utilisateur..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          leftIcon={<Search size={18} />}
        />
      </div>

      {/* Erreur */}
      {error && (
        <div className="px-4 py-3 rounded-lg bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-red-700 dark:text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 rounded-lg bg-light-200 dark:bg-dark-700 animate-pulse" />
          ))}
        </div>
      ) : (
        /* Table des utilisateurs */
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="table-header-oto">
                  <th className="text-left px-6 py-3 text-xs font-bold uppercase tracking-wider">Utilisateur</th>
                  <th className="text-left px-6 py-3 text-xs font-bold uppercase tracking-wider">Email</th>
                  <th className="text-left px-6 py-3 text-xs font-bold uppercase tracking-wider">Rôle</th>
                  <th className="text-left px-6 py-3 text-xs font-bold uppercase tracking-wider">Statut</th>
                  <th className="text-left px-6 py-3 text-xs font-bold uppercase tracking-wider">Créé le</th>
                  <th className="text-right px-6 py-3 text-xs font-bold uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-light-200 dark:divide-dark-700">
                {filteredUsers.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-12 text-center text-gray-500 dark:text-dark-400">
                      {search ? 'Aucun utilisateur trouvé' : 'Aucun utilisateur'}
                    </td>
                  </tr>
                ) : (
                  filteredUsers.map((u) => (
                    <UserRow
                      key={u.id}
                      user={u}
                      isCurrentUser={u.id === currentUser?.id}
                      onEdit={() => setEditUser(u)}
                      onResetPassword={() => setResetPasswordUser(u)}
                      onDelete={() => setDeleteUser(u)}
                      onToggleActive={async () => {
                        try {
                          await adminApi.updateUser(u.id, { is_active: !u.is_active });
                          showFeedback('success', `${u.username} ${u.is_active ? 'désactivé' : 'activé'}`);
                          loadUsers();
                        } catch {
                          showFeedback('error', 'Erreur lors de la modification');
                        }
                      }}
                    />
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Stats rapides */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatBox
          icon={<Users size={20} />}
          label="Total"
          value={users.length}
          color="oto"
        />
        <StatBox
          icon={<ShieldCheck size={20} />}
          label="Administrateurs"
          value={users.filter((u) => u.role === 'admin').length}
          color="green"
        />
        <StatBox
          icon={<UserX size={20} />}
          label="Désactivés"
          value={users.filter((u) => !u.is_active).length}
          color="red"
        />
      </div>

      {/* Demandes de déploiement en attente */}
      <PendingApprovalsSection showFeedback={showFeedback} />

      {/* Journal d'audit */}
      <AuditLogSection />

      {/* Modal Création */}
      {showCreateModal && (
        <CreateUserModal
          onClose={() => setShowCreateModal(false)}
          onSuccess={() => {
            setShowCreateModal(false);
            showFeedback('success', 'Utilisateur créé avec succès');
            loadUsers();
          }}
          onError={(msg) => showFeedback('error', msg)}
        />
      )}

      {/* Modal Édition */}
      {editUser && (
        <EditUserModal
          user={editUser}
          onClose={() => setEditUser(null)}
          onSuccess={() => {
            setEditUser(null);
            showFeedback('success', 'Utilisateur modifié avec succès');
            loadUsers();
          }}
          onError={(msg) => showFeedback('error', msg)}
        />
      )}

      {/* Modal Reset Password */}
      {resetPasswordUser && (
        <ResetPasswordModal
          user={resetPasswordUser}
          onClose={() => setResetPasswordUser(null)}
          onSuccess={() => {
            setResetPasswordUser(null);
            showFeedback('success', 'Mot de passe réinitialisé');
          }}
          onError={(msg) => showFeedback('error', msg)}
        />
      )}

      {/* Modal Suppression */}
      {deleteUser && (
        <ConfirmModal
          isOpen
          title="Supprimer l'utilisateur"
          message={`Voulez-vous vraiment supprimer "${deleteUser.username}" ? Cette action est irréversible.`}
          confirmText="Supprimer"
          variant="danger"
          onClose={() => setDeleteUser(null)}
          onConfirm={async () => {
            try {
              await adminApi.deleteUser(deleteUser.id);
              setDeleteUser(null);
              showFeedback('success', `Utilisateur "${deleteUser.username}" supprimé`);
              loadUsers();
            } catch (err: any) {
              const msg = err?.response?.data?.detail || 'Erreur lors de la suppression';
              showFeedback('error', msg);
              setDeleteUser(null);
            }
          }}
        />
      )}
      </div>
    </div>
  );
}

// =============================================================================
// Sous-composants
// =============================================================================

function UserRow({
  user,
  isCurrentUser,
  onEdit,
  onResetPassword,
  onDelete,
  onToggleActive,
}: {
  user: AdminUser;
  isCurrentUser: boolean;
  onEdit: () => void;
  onResetPassword: () => void;
  onDelete: () => void;
  onToggleActive: () => void;
}) {
  return (
    <tr className="hover:bg-light-50 dark:hover:bg-dark-800/50 transition-colors">
      {/* Utilisateur */}
      <td className="px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-oto-100 dark:bg-oto-500/20 flex items-center justify-center text-oto-600 dark:text-oto-400 font-bold text-sm uppercase">
            {user.username.charAt(0)}
          </div>
          <div>
            <div className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
              {user.username}
              {isCurrentUser && (
                <span className="text-[10px] px-1.5 py-0.5 bg-oto-100 dark:bg-oto-500/20 text-oto-600 dark:text-oto-400 rounded-full font-bold">
                  VOUS
                </span>
              )}
            </div>
            {user.full_name && (
              <span className="text-xs text-gray-500 dark:text-dark-400">{user.full_name}</span>
            )}
          </div>
        </div>
      </td>

      {/* Email */}
      <td className="px-6 py-4 text-sm text-gray-600 dark:text-dark-300">{user.email}</td>

      {/* Rôle */}
      <td className="px-6 py-4">
        <RoleBadge role={user.role} />
      </td>

      {/* Statut */}
      <td className="px-6 py-4">
        <span
          className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full border ${
            user.is_active
              ? 'bg-green-50 dark:bg-green-500/10 text-green-700 dark:text-green-400 border-green-200 dark:border-green-500/20'
              : 'bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400 border-red-200 dark:border-red-500/20'
          }`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${user.is_active ? 'bg-green-500' : 'bg-red-500'}`} />
          {user.is_active ? 'Actif' : 'Désactivé'}
        </span>
      </td>

      {/* Date */}
      <td className="px-6 py-4 text-sm text-gray-500 dark:text-dark-400">
        {new Date(user.created_at).toLocaleDateString('fr-FR', {
          day: '2-digit',
          month: '2-digit',
          year: 'numeric',
        })}
      </td>

      {/* Actions */}
      <td className="px-6 py-4">
        <div className="flex items-center justify-end gap-1">
          <button
            onClick={onEdit}
            className="p-2 rounded-lg text-gray-500 dark:text-dark-400 hover:bg-oto-50 dark:hover:bg-dark-700 hover:text-oto-600 dark:hover:text-oto-400 transition-colors"
            title="Modifier"
          >
            <Pencil size={16} />
          </button>
          <button
            onClick={onResetPassword}
            className="p-2 rounded-lg text-gray-500 dark:text-dark-400 hover:bg-yellow-50 dark:hover:bg-yellow-500/10 hover:text-yellow-600 dark:hover:text-yellow-400 transition-colors"
            title="Réinitialiser le mot de passe"
          >
            <KeyRound size={16} />
          </button>
          {!isCurrentUser && (
            <>
              <button
                onClick={onToggleActive}
                className={`p-2 rounded-lg transition-colors ${
                  user.is_active
                    ? 'text-gray-500 dark:text-dark-400 hover:bg-orange-50 dark:hover:bg-orange-500/10 hover:text-orange-600 dark:hover:text-orange-400'
                    : 'text-gray-500 dark:text-dark-400 hover:bg-green-50 dark:hover:bg-green-500/10 hover:text-green-600 dark:hover:text-green-400'
                }`}
                title={user.is_active ? 'Désactiver' : 'Activer'}
              >
                {user.is_active ? <UserX size={16} /> : <UserCheck size={16} />}
              </button>
              <button
                onClick={onDelete}
                className="p-2 rounded-lg text-gray-500 dark:text-dark-400 hover:bg-red-50 dark:hover:bg-red-500/10 hover:text-red-600 dark:hover:text-red-400 transition-colors"
                title="Supprimer"
              >
                <Trash2 size={16} />
              </button>
            </>
          )}
        </div>
      </td>
    </tr>
  );
}

function RoleBadge({ role }: { role: UserRole }) {
  if (role === 'admin') {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-bold px-2.5 py-1 rounded-full bg-purple-100 dark:bg-purple-500/10 text-purple-700 dark:text-purple-400 border border-purple-200 dark:border-purple-500/20">
        <ShieldCheck size={13} />
        Admin
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-bold px-2.5 py-1 rounded-full bg-gray-100 dark:bg-dark-600/50 text-gray-600 dark:text-dark-300 border border-gray-200 dark:border-dark-500/20">
      <Shield size={13} />
      Utilisateur
    </span>
  );
}

function StatBox({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  color: string;
}) {
  const colorMap: Record<string, string> = {
    oto: 'bg-oto-50 dark:bg-oto-500/10 text-oto-600 dark:text-oto-400',
    green: 'bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400',
    red: 'bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400',
  };

  return (
    <div className="card p-4 flex items-center gap-4">
      <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${colorMap[color]}`}>{icon}</div>
      <div>
        <p className="text-2xl font-black text-gray-900 dark:text-white">{value}</p>
        <p className="text-xs text-gray-500 dark:text-dark-400 uppercase tracking-wide font-medium">{label}</p>
      </div>
    </div>
  );
}

// =============================================================================
// Modal Création
// =============================================================================

function CreateUserModal({
  onClose,
  onSuccess,
  onError,
}: {
  onClose: () => void;
  onSuccess: () => void;
  onError: (msg: string) => void;
}) {
  const [form, setForm] = useState({ username: '', email: '', password: '', full_name: '' });
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const validate = () => {
    const e: Record<string, string> = {};
    if (!form.username.trim()) e.username = 'Requis';
    if (!form.email.trim()) e.email = 'Requis';
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) e.email = 'Email invalide';
    if (!form.password) e.password = 'Requis';
    else if (form.password.length < 8) e.password = 'Minimum 8 caractères';
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) return;
    setSaving(true);
    try {
      await adminApi.createUser({
        username: form.username.trim(),
        email: form.email.trim(),
        password: form.password,
        full_name: form.full_name.trim() || undefined,
      });
      onSuccess();
    } catch (err: any) {
      onError(err?.response?.data?.detail || 'Erreur lors de la création');
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      isOpen
      onClose={onClose}
      title="Nouvel utilisateur"
      size="md"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            Annuler
          </Button>
          <Button onClick={handleSubmit} isLoading={saving} leftIcon={<UserPlus size={16} />}>
            Créer
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input
          label="Nom d'utilisateur"
          required
          value={form.username}
          onChange={(e) => setForm({ ...form, username: e.target.value })}
          error={errors.username}
          placeholder="jean.dupont"
        />
        <Input
          label="Email"
          required
          type="email"
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
          error={errors.email}
          placeholder="jean.dupont@oto-technology.fr"
        />
        <Input
          label="Nom complet"
          value={form.full_name}
          onChange={(e) => setForm({ ...form, full_name: e.target.value })}
          placeholder="Jean Dupont"
        />
        <Input
          label="Mot de passe"
          required
          type="password"
          value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })}
          error={errors.password}
          helperText="Minimum 8 caractères"
        />
        <p className="text-xs text-gray-500 dark:text-dark-400">
          L'utilisateur sera créé avec le rôle <strong>Utilisateur</strong> par défaut.
          Vous pourrez le modifier après la création.
        </p>
      </div>
    </Modal>
  );
}

// =============================================================================
// Modal Édition
// =============================================================================

function EditUserModal({
  user,
  onClose,
  onSuccess,
  onError,
}: {
  user: AdminUser;
  onClose: () => void;
  onSuccess: () => void;
  onError: (msg: string) => void;
}) {
  const [form, setForm] = useState({
    full_name: user.full_name || '',
    role: user.role as string,
    is_active: user.is_active,
  });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    setSaving(true);
    try {
      await adminApi.updateUser(user.id, {
        full_name: form.full_name.trim() || null,
        role: form.role as UserRole,
        is_active: form.is_active,
      });
      onSuccess();
    } catch (err: any) {
      onError(err?.response?.data?.detail || 'Erreur lors de la modification');
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      isOpen
      onClose={onClose}
      title={`Modifier ${user.username}`}
      size="md"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            Annuler
          </Button>
          <Button onClick={handleSubmit} isLoading={saving} leftIcon={<Pencil size={16} />}>
            Enregistrer
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input
          label="Nom complet"
          value={form.full_name}
          onChange={(e) => setForm({ ...form, full_name: e.target.value })}
          placeholder="Jean Dupont"
        />
        <Select
          label="Rôle"
          value={form.role}
          onChange={(e) => setForm({ ...form, role: e.target.value })}
          options={[
            { value: 'admin', label: 'Administrateur' },
            { value: 'user', label: 'Utilisateur' },
          ]}
        />
        <div className="flex items-center justify-between p-3 rounded-lg bg-light-50 dark:bg-dark-700/50 border border-light-200 dark:border-dark-600">
          <div>
            <p className="text-sm font-medium text-gray-900 dark:text-white">Compte actif</p>
            <p className="text-xs text-gray-500 dark:text-dark-400">
              Un compte désactivé ne peut plus se connecter
            </p>
          </div>
          <button
            onClick={() => setForm({ ...form, is_active: !form.is_active })}
            className={`relative w-11 h-6 rounded-full transition-colors ${
              form.is_active ? 'bg-green-500' : 'bg-gray-300 dark:bg-dark-600'
            }`}
          >
            <span
              className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
                form.is_active ? 'translate-x-5' : 'translate-x-0'
              }`}
            />
          </button>
        </div>
      </div>
    </Modal>
  );
}

// =============================================================================
// Modal Reset Password
// =============================================================================

function ResetPasswordModal({
  user,
  onClose,
  onSuccess,
  onError,
}: {
  user: AdminUser;
  onClose: () => void;
  onSuccess: () => void;
  onError: (msg: string) => void;
}) {
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const validate = () => {
    const e: Record<string, string> = {};
    if (!password) e.password = 'Requis';
    else if (password.length < 8) e.password = 'Minimum 8 caractères';
    if (password !== confirm) e.confirm = 'Les mots de passe ne correspondent pas';
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) return;
    setSaving(true);
    try {
      await adminApi.resetPassword(user.id, { new_password: password });
      onSuccess();
    } catch (err: any) {
      onError(err?.response?.data?.detail || 'Erreur lors de la réinitialisation');
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      isOpen
      onClose={onClose}
      title={`Réinitialiser le mot de passe`}
      size="md"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            Annuler
          </Button>
          <Button onClick={handleSubmit} isLoading={saving} variant="danger" leftIcon={<KeyRound size={16} />}>
            Réinitialiser
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="flex items-center gap-3 p-3 rounded-lg bg-yellow-50 dark:bg-yellow-500/10 border border-yellow-200 dark:border-yellow-500/20">
          <AlertTriangle size={18} className="text-yellow-600 dark:text-yellow-400 flex-shrink-0" />
          <p className="text-sm text-yellow-700 dark:text-yellow-300">
            Vous allez réinitialiser le mot de passe de <strong>{user.username}</strong>.
            L'utilisateur devra utiliser le nouveau mot de passe pour se connecter.
          </p>
        </div>
        <Input
          label="Nouveau mot de passe"
          required
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
          helperText="Minimum 8 caractères"
        />
        <Input
          label="Confirmer le mot de passe"
          required
          type="password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          error={errors.confirm}
        />
      </div>
    </Modal>
  );
}

// =============================================================================
// Demandes de déploiement en attente
// =============================================================================

function PendingApprovalsSection({
  showFeedback,
}: {
  showFeedback: (type: 'success' | 'error', message: string) => void;
}) {
  const [pending, setPending] = useState<Deployment[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(true);
  const [rejectModal, setRejectModal] = useState<Deployment | null>(null);
  const [rejectNote, setRejectNote] = useState('');

  const loadPending = async () => {
    try {
      setLoading(true);
      const data = await deploymentsApi.listPendingApprovals();
      setPending(data);
    } catch {
      // Silently fail
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPending();
    const interval = setInterval(loadPending, 15000);
    return () => clearInterval(interval);
  }, []);

  const handleApprove = async (deployment: Deployment) => {
    try {
      await deploymentsApi.approve(deployment.id);
      showFeedback('success', `Déploiement "${deployment.vm_name}" approuvé et lancé`);
      loadPending();
    } catch (err: any) {
      showFeedback('error', err?.response?.data?.detail || "Erreur lors de l'approbation");
    }
  };

  const handleReject = async () => {
    if (!rejectModal || !rejectNote.trim()) return;
    try {
      await deploymentsApi.reject(rejectModal.id, rejectNote);
      showFeedback('success', `Déploiement "${rejectModal.vm_name}" refusé`);
      setRejectModal(null);
      setRejectNote('');
      loadPending();
    } catch (err: any) {
      showFeedback('error', err?.response?.data?.detail || 'Erreur lors du refus');
    }
  };

  return (
    <>
      <div className="card overflow-hidden">
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center justify-between px-6 py-4 hover:bg-light-50 dark:hover:bg-dark-800/50 transition-colors"
        >
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-yellow-100 dark:bg-yellow-500/20 rounded-lg flex items-center justify-center">
              <Clock size={18} className="text-yellow-600 dark:text-yellow-400" />
            </div>
            <h2 className="text-lg font-bold text-gray-900 dark:text-white">
              Demandes de déploiement
            </h2>
            {pending.length > 0 && (
              <span className="px-2 py-0.5 bg-yellow-100 dark:bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 text-xs font-bold rounded-full">
                {pending.length}
              </span>
            )}
          </div>
          {expanded ? <ChevronUp size={20} className="text-gray-400" /> : <ChevronDown size={20} className="text-gray-400" />}
        </button>

        {expanded && (
          <div className="border-t border-light-200 dark:border-dark-700">
            {loading ? (
              <div className="px-6 py-8 text-center text-gray-500 dark:text-dark-400">
                Chargement...
              </div>
            ) : pending.length === 0 ? (
              <div className="px-6 py-8 text-center text-gray-500 dark:text-dark-400">
                Aucune demande en attente
              </div>
            ) : (
              <div className="divide-y divide-light-200 dark:divide-dark-700">
                {pending.map((d) => (
                  <div key={d.id} className="px-6 py-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <Rocket size={18} className="text-yellow-500" />
                      <div>
                        <p className="font-semibold text-gray-900 dark:text-white">{d.vm_name}</p>
                        <p className="text-xs text-gray-500 dark:text-dark-400">
                          Demandé par <strong>{d.requested_by_username || '?'}</strong> le{' '}
                          {new Date(d.created_at).toLocaleDateString('fr-FR', {
                            day: '2-digit',
                            month: '2-digit',
                            year: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </p>
                        <p className="text-xs text-gray-400 dark:text-dark-500 mt-0.5">
                          {d.config?.cpu_count || '?'} vCPU &middot; {d.config?.ram_gb || '?'} GB RAM &middot; {d.config?.disk_gb || '?'} GB Disque
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        variant="secondary"
                        leftIcon={<XCircle size={14} />}
                        onClick={() => setRejectModal(d)}
                      >
                        Refuser
                      </Button>
                      <Button
                        size="sm"
                        leftIcon={<CheckCircle size={14} />}
                        onClick={() => handleApprove(d)}
                      >
                        Approuver
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Modal de refus */}
      {rejectModal && (
        <Modal
          isOpen
          onClose={() => { setRejectModal(null); setRejectNote(''); }}
          title="Refuser le déploiement"
          size="md"
          footer={
            <>
              <Button variant="secondary" onClick={() => { setRejectModal(null); setRejectNote(''); }}>
                Annuler
              </Button>
              <Button variant="danger" onClick={handleReject} disabled={!rejectNote.trim()} leftIcon={<XCircle size={16} />}>
                Refuser
              </Button>
            </>
          }
        >
          <div className="space-y-4">
            <div className="flex items-center gap-3 p-3 rounded-lg bg-yellow-50 dark:bg-yellow-500/10 border border-yellow-200 dark:border-yellow-500/20">
              <AlertTriangle size={18} className="text-yellow-600 dark:text-yellow-400 flex-shrink-0" />
              <p className="text-sm text-yellow-700 dark:text-yellow-300">
                Vous refusez le déploiement <strong>"{rejectModal.vm_name}"</strong> demandé par <strong>{rejectModal.requested_by_username}</strong>.
              </p>
            </div>
            <Input
              label="Raison du refus"
              required
              value={rejectNote}
              onChange={(e) => setRejectNote(e.target.value)}
              placeholder="Expliquez la raison du refus..."
            />
          </div>
        </Modal>
      )}
    </>
  );
}

// =============================================================================
// Journal d'audit
// =============================================================================

const ACTION_LABELS: Record<string, { label: string; color: string }> = {
  deployment_requested: { label: 'Demande de déploiement', color: 'text-yellow-600 dark:text-yellow-400' },
  deployment_created: { label: 'Déploiement créé', color: 'text-blue-600 dark:text-blue-400' },
  deployment_approved: { label: 'Déploiement approuvé', color: 'text-green-600 dark:text-green-400' },
  deployment_rejected: { label: 'Déploiement refusé', color: 'text-red-600 dark:text-red-400' },
  user_created: { label: 'Utilisateur créé', color: 'text-blue-600 dark:text-blue-400' },
  user_updated: { label: 'Utilisateur modifié', color: 'text-orange-600 dark:text-orange-400' },
  user_deleted: { label: 'Utilisateur supprimé', color: 'text-red-600 dark:text-red-400' },
};

function AuditLogSection() {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  const loadLogs = async (p = 1) => {
    try {
      setLoading(true);
      const data = await deploymentsApi.getAuditLog({ page: p, page_size: 20 });
      setLogs(data.items);
      setTotal(data.total);
      setPage(p);
    } catch {
      // Silently fail
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (expanded) loadLogs();
  }, [expanded]);

  const totalPages = Math.ceil(total / 20);

  return (
    <div className="card overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-6 py-4 hover:bg-light-50 dark:hover:bg-dark-800/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-gray-100 dark:bg-dark-600 rounded-lg flex items-center justify-center">
            <ScrollText size={18} className="text-gray-600 dark:text-dark-300" />
          </div>
          <h2 className="text-lg font-bold text-gray-900 dark:text-white">
            Journal d'audit
          </h2>
        </div>
        {expanded ? <ChevronUp size={20} className="text-gray-400" /> : <ChevronDown size={20} className="text-gray-400" />}
      </button>

      {expanded && (
        <div className="border-t border-light-200 dark:border-dark-700">
          {loading ? (
            <div className="px-6 py-8 text-center text-gray-500 dark:text-dark-400">
              Chargement...
            </div>
          ) : logs.length === 0 ? (
            <div className="px-6 py-8 text-center text-gray-500 dark:text-dark-400">
              Aucune activité enregistrée
            </div>
          ) : (
            <>
              <div className="divide-y divide-light-200 dark:divide-dark-700">
                {logs.map((log) => {
                  const actionInfo = ACTION_LABELS[log.action] || { label: log.action, color: 'text-gray-600 dark:text-gray-400' };
                  return (
                    <div key={log.id} className="px-6 py-3 flex items-start gap-3">
                      <div className="text-xs text-gray-400 dark:text-dark-500 w-32 flex-shrink-0 pt-0.5">
                        {new Date(log.created_at).toLocaleDateString('fr-FR', {
                          day: '2-digit',
                          month: '2-digit',
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm">
                          <span className="font-semibold text-gray-900 dark:text-white">{log.username}</span>
                          {' — '}
                          <span className={`font-medium ${actionInfo.color}`}>{actionInfo.label}</span>
                        </p>
                        {log.details && (
                          <p className="text-xs text-gray-500 dark:text-dark-400 mt-0.5 truncate">
                            {log.details.vm_name && `VM: ${log.details.vm_name}`}
                            {log.details.requested_by && ` (demandé par ${log.details.requested_by})`}
                            {log.details.reason && ` — ${log.details.reason}`}
                            {log.details.note && ` — ${log.details.note}`}
                          </p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
              {totalPages > 1 && (
                <div className="px-6 py-3 border-t border-light-200 dark:border-dark-700 flex items-center justify-between">
                  <span className="text-xs text-gray-500 dark:text-dark-400">
                    {total} entrée{total > 1 ? 's' : ''}
                  </span>
                  <div className="flex items-center gap-2">
                    <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => loadLogs(page - 1)}>
                      Précédent
                    </Button>
                    <span className="text-xs text-gray-500 dark:text-dark-400">
                      {page}/{totalPages}
                    </span>
                    <Button size="sm" variant="secondary" disabled={page >= totalPages} onClick={() => loadLogs(page + 1)}>
                      Suivant
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
