import React, { useState, useEffect, useRef } from 'react';
import { config } from '@/config/environment';
import toastService from '@/services/toast';

const API_BASE_URL = config.urls.api;

export default function SoportePanel() {
  // Tab control
  const [activeTab, setActiveTab] = useState('no-photo');

  // No-photo users state
  const [noPhotoUsers, setNoPhotoUsers] = useState([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [sendingAll, setSendingAll] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);
  const [sendingIndividual, setSendingIndividual] = useState({});

  // Individual photo request state
  const [photoRfc, setPhotoRfc] = useState('');
  const [sendingPhotoRfc, setSendingPhotoRfc] = useState(false);
  const [photoRfcResult, setPhotoRfcResult] = useState(null);

  // Resend cert state
  const [certRfc, setCertRfc] = useState('');
  const [sendingCert, setSendingCert] = useState(false);
  const [certResult, setCertResult] = useState(null);

  // Logs state
  const [logs, setLogs] = useState([]);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [logSearch, setLogSearch] = useState('');
  const [logLevel, setLogLevel] = useState('');
  const [logLimit, setLogLimit] = useState(100);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const logsEndRef = useRef(null);
  const autoRefreshRef = useRef(null);

  // ========== No-photo users ==========
  const loadNoPhotoUsers = async () => {
    setLoadingUsers(true);
    try {
      const resp = await fetch(`${API_BASE_URL}/v1/onboarding/support/no-photo-users`);
      const data = await resp.json();
      if (data.success) {
        setNoPhotoUsers(data.users);
        toastService.info(`${data.total} usuarios aprobados sin foto`);
      }
    } catch (e) {
      toastService.error('Error al cargar usuarios');
    } finally {
      setLoadingUsers(false);
    }
  };

  const sendAllPhotoRequests = async () => {
    if (!confirm(`Se enviarán correos a ${noPhotoUsers.length} usuarios. ¿Continuar?`)) return;
    setSendingAll(true);
    setBulkResult(null);
    try {
      const resp = await fetch(`${API_BASE_URL}/v1/onboarding/support/send-all-photo-requests`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await resp.json();
      setBulkResult(data);
      toastService.success(`Enviados: ${data.sent} | Fallidos: ${data.failed}`);
    } catch (e) {
      toastService.error('Error al enviar correos masivos');
    } finally {
      setSendingAll(false);
    }
  };

  const sendIndividualPhotoRequest = async (rfc) => {
    setSendingIndividual(prev => ({ ...prev, [rfc]: true }));
    try {
      const resp = await fetch(`${API_BASE_URL}/v1/onboarding/send-photo-update-request/${rfc}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await resp.json();
      if (data.success) {
        toastService.success(`Correo enviado a ${data.email_masked}`);
      } else {
        toastService.warning(data.message);
      }
    } catch (e) {
      toastService.error(`Error al enviar correo a ${rfc}`);
    } finally {
      setSendingIndividual(prev => ({ ...prev, [rfc]: false }));
    }
  };

  // ========== Individual photo request ==========
  const sendPhotoRequestByRfc = async () => {
    if (!photoRfc.trim()) return;
    setSendingPhotoRfc(true);
    setPhotoRfcResult(null);
    try {
      const resp = await fetch(`${API_BASE_URL}/v1/onboarding/send-photo-update-request/${photoRfc.trim().toUpperCase()}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await resp.json();
      setPhotoRfcResult(data);
      if (data.success) {
        toastService.success(`Correo enviado a ${data.email_masked}`);
      } else {
        toastService.warning(data.message || 'No se pudo enviar');
      }
    } catch (e) {
      toastService.error('Error al enviar correo');
      setPhotoRfcResult({ success: false, message: 'Error de conexión' });
    } finally {
      setSendingPhotoRfc(false);
    }
  };

  // ========== Resend cert ==========
  const resendCert = async () => {
    if (!certRfc.trim()) return;
    setSendingCert(true);
    setCertResult(null);
    try {
      const resp = await fetch(`${API_BASE_URL}/v1/onboarding/support/resend-cert/${certRfc.trim().toUpperCase()}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await resp.json();
      setCertResult(data);
      if (data.success) {
        toastService.success(`Certificado reenviado a ${data.email_masked}`);
      } else {
        toastService.error(data.message || data.detail || 'Error al reenviar');
      }
    } catch (e) {
      toastService.error('Error al reenviar certificado');
      setCertResult({ success: false, message: 'Error de conexión' });
    } finally {
      setSendingCert(false);
    }
  };

  // ========== Logs ==========
  const fetchLogs = async () => {
    setLoadingLogs(true);
    try {
      const params = new URLSearchParams({ limit: logLimit });
      if (logSearch.trim()) params.set('search', logSearch.trim());
      if (logLevel) params.set('level', logLevel);

      const resp = await fetch(`${API_BASE_URL}/v1/onboarding/support/logs?${params}`);
      const data = await resp.json();
      if (data.success) {
        setLogs(data.logs);
      }
    } catch (e) {
      toastService.error('Error al cargar logs');
    } finally {
      setLoadingLogs(false);
    }
  };

  useEffect(() => {
    if (autoRefresh) {
      autoRefreshRef.current = setInterval(fetchLogs, 5000);
    } else if (autoRefreshRef.current) {
      clearInterval(autoRefreshRef.current);
    }
    return () => { if (autoRefreshRef.current) clearInterval(autoRefreshRef.current); };
  }, [autoRefresh, logSearch, logLevel, logLimit]);

  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  const levelColors = {
    error: 'bg-red-100 text-red-800 border-red-300',
    warning: 'bg-yellow-100 text-yellow-800 border-yellow-300',
    info: 'bg-gray-50 text-gray-700 border-gray-200',
  };

  const levelBadgeColors = {
    error: 'bg-red-600',
    warning: 'bg-amber-500',
    info: 'bg-blue-500',
  };

  const highlightText = (text, search) => {
    if (!search) return text;
    const regex = new RegExp(`(${search.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    const parts = text.split(regex);
    return parts.map((part, i) =>
      regex.test(part) ? <span key={i} className="bg-yellow-400 text-black px-0.5 rounded">{part}</span> : part
    );
  };

  const tabs = [
    { id: 'no-photo', label: 'Sin Foto', icon: '📷' },
    { id: 'photo-individual', label: 'Solicitar Foto', icon: '✉️' },
    { id: 'resend-cert', label: 'Reenviar Certificado', icon: '📄' },
    { id: 'logs', label: 'Logs', icon: '🔍' },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <img src="/onboarding-assets/images/coca-cola-femsa-logo.png" alt="FEMSA" className="h-12" />
            <div>
              <h1 className="text-xl font-bold text-gray-800">Panel de Soporte</h1>
              <p className="text-sm text-gray-500">Onboarding Seguridad KOF</p>
            </div>
          </div>
        </div>
      </header>

      {/* Tabs */}
      <div className="max-w-5xl mx-auto px-4 mt-6">
        <div className="flex gap-1 bg-white rounded-lg shadow-sm p-1">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 py-3 px-4 rounded-md text-sm font-medium transition-all ${
                activeTab === tab.id
                  ? 'bg-red-600 text-white shadow-sm'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              <span className="mr-2">{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <main className="max-w-5xl mx-auto px-4 py-6">
        {/* ========== TAB 1: Sin foto ========== */}
        {activeTab === 'no-photo' && (
          <div className="bg-white rounded-lg shadow-sm p-6">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-lg font-bold text-gray-800">Usuarios Aprobados Sin Foto</h2>
                <p className="text-sm text-gray-500">Colaboradores que necesitan actualizar su foto de credencial</p>
              </div>
              <div className="flex gap-3">
                <button
                  onClick={loadNoPhotoUsers}
                  disabled={loadingUsers}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
                >
                  {loadingUsers ? 'Cargando...' : 'Cargar Lista'}
                </button>
                {noPhotoUsers.length > 0 && (
                  <button
                    onClick={sendAllPhotoRequests}
                    disabled={sendingAll}
                    className="px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 disabled:opacity-50"
                  >
                    {sendingAll ? 'Enviando...' : `Enviar a Todos (${noPhotoUsers.length})`}
                  </button>
                )}
              </div>
            </div>

            {bulkResult && (
              <div className={`mb-4 p-4 rounded-lg ${bulkResult.failed > 0 ? 'bg-yellow-50 border border-yellow-200' : 'bg-green-50 border border-green-200'}`}>
                <p className="font-medium">
                  Resultado: <span className="text-green-700">{bulkResult.sent} enviados</span>
                  {bulkResult.failed > 0 && <span className="text-red-700 ml-2">{bulkResult.failed} fallidos</span>}
                </p>
              </div>
            )}

            {noPhotoUsers.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 text-left">
                      <th className="px-4 py-3 font-medium text-gray-600">#</th>
                      <th className="px-4 py-3 font-medium text-gray-600">Nombre</th>
                      <th className="px-4 py-3 font-medium text-gray-600">RFC</th>
                      <th className="px-4 py-3 font-medium text-gray-600">Email</th>
                      <th className="px-4 py-3 font-medium text-gray-600">Proveedor</th>
                      <th className="px-4 py-3 font-medium text-gray-600 text-center">Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {noPhotoUsers.map((user, i) => (
                      <tr key={user.rfc + i} className="border-t border-gray-100 hover:bg-gray-50">
                        <td className="px-4 py-3 text-gray-400">{i + 1}</td>
                        <td className="px-4 py-3 font-medium text-gray-800">{user.nombre}</td>
                        <td className="px-4 py-3 text-gray-600 font-mono text-xs">{user.rfc}</td>
                        <td className="px-4 py-3 text-gray-600 text-xs">{user.email}</td>
                        <td className="px-4 py-3 text-gray-600 text-xs">{user.proveedor}</td>
                        <td className="px-4 py-3 text-center">
                          <button
                            onClick={() => sendIndividualPhotoRequest(user.rfc)}
                            disabled={sendingIndividual[user.rfc]}
                            className="px-3 py-1.5 bg-amber-500 text-white rounded text-xs font-medium hover:bg-amber-600 disabled:opacity-50"
                          >
                            {sendingIndividual[user.rfc] ? 'Enviando...' : 'Enviar Correo'}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {!loadingUsers && noPhotoUsers.length === 0 && (
              <div className="text-center py-12 text-gray-400">
                <p className="text-4xl mb-3">📷</p>
                <p>Haz clic en "Cargar Lista" para ver los usuarios sin foto</p>
              </div>
            )}
          </div>
        )}

        {/* ========== TAB 2: Solicitar foto individual ========== */}
        {activeTab === 'photo-individual' && (
          <div className="bg-white rounded-lg shadow-sm p-6 max-w-lg mx-auto">
            <h2 className="text-lg font-bold text-gray-800 mb-2">Solicitar Actualización de Foto</h2>
            <p className="text-sm text-gray-500 mb-6">
              Envía el correo de solicitud obligatoria de foto a un colaborador específico
            </p>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">RFC del Colaborador</label>
                <input
                  type="text"
                  value={photoRfc}
                  onChange={e => { setPhotoRfc(e.target.value.toUpperCase()); setPhotoRfcResult(null); }}
                  placeholder="Ej: SAML970804196"
                  maxLength={13}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 focus:border-red-500 font-mono uppercase"
                />
              </div>

              <button
                onClick={sendPhotoRequestByRfc}
                disabled={sendingPhotoRfc || !photoRfc.trim()}
                className="w-full py-3 bg-amber-500 text-white rounded-lg font-medium hover:bg-amber-600 disabled:opacity-50 transition-colors"
              >
                {sendingPhotoRfc ? 'Enviando...' : 'Enviar Solicitud de Foto'}
              </button>

              {photoRfcResult && (
                <div className={`p-4 rounded-lg ${photoRfcResult.success ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
                  <p className={`font-medium ${photoRfcResult.success ? 'text-green-800' : 'text-red-800'}`}>
                    {photoRfcResult.success ? '✓' : '✗'} {photoRfcResult.message}
                  </p>
                  {photoRfcResult.nombre && (
                    <p className="text-sm text-gray-600 mt-1">Nombre: {photoRfcResult.nombre}</p>
                  )}
                  {photoRfcResult.email_masked && (
                    <p className="text-sm text-gray-600">Enviado a: {photoRfcResult.email_masked}</p>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ========== TAB 3: Reenviar certificado ========== */}
        {activeTab === 'resend-cert' && (
          <div className="bg-white rounded-lg shadow-sm p-6 max-w-lg mx-auto">
            <h2 className="text-lg font-bold text-gray-800 mb-2">Reenviar Certificado</h2>
            <p className="text-sm text-gray-500 mb-6">
              Reenvía el correo con el certificado, QR y PDF al email registrado del colaborador
            </p>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">RFC del Colaborador</label>
                <input
                  type="text"
                  value={certRfc}
                  onChange={e => { setCertRfc(e.target.value.toUpperCase()); setCertResult(null); }}
                  placeholder="Ej: COTA900616L56"
                  maxLength={13}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 focus:border-red-500 font-mono uppercase"
                />
              </div>

              <button
                onClick={resendCert}
                disabled={sendingCert || !certRfc.trim()}
                className="w-full py-3 bg-red-600 text-white rounded-lg font-medium hover:bg-red-700 disabled:opacity-50 transition-colors"
              >
                {sendingCert ? 'Enviando...' : 'Reenviar Certificado'}
              </button>

              {certResult && (
                <div className={`p-4 rounded-lg ${certResult.success ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
                  <p className={`font-medium ${certResult.success ? 'text-green-800' : 'text-red-800'}`}>
                    {certResult.success ? '✓' : '✗'} {certResult.message || certResult.detail}
                  </p>
                  {certResult.nombre && (
                    <p className="text-sm text-gray-600 mt-1">Nombre: {certResult.nombre}</p>
                  )}
                  {certResult.email_masked && (
                    <p className="text-sm text-gray-600">Enviado a: {certResult.email_masked}</p>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ========== TAB 4: Logs ========== */}
        {activeTab === 'logs' && (
          <div className="bg-white rounded-lg shadow-sm p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-bold text-gray-800">Logs del Sistema</h2>
                <p className="text-sm text-gray-500">Monitoreo de envíos, errores y actividad</p>
              </div>
              <div className="flex items-center gap-2">
                <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={autoRefresh}
                    onChange={e => setAutoRefresh(e.target.checked)}
                    className="rounded"
                  />
                  Auto-refresh
                </label>
                {autoRefresh && <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />}
              </div>
            </div>

            {/* Filters */}
            <div className="flex flex-wrap gap-3 mb-4">
              <input
                type="text"
                value={logSearch}
                onChange={e => setLogSearch(e.target.value)}
                placeholder="Buscar RFC, email, error..."
                className="flex-1 min-w-[200px] px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-red-500 focus:border-red-500"
              />
              <select
                value={logLevel}
                onChange={e => setLogLevel(e.target.value)}
                className="px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white"
              >
                <option value="">Todos los niveles</option>
                <option value="error">Errores</option>
                <option value="warning">Warnings</option>
                <option value="info">Info</option>
              </select>
              <select
                value={logLimit}
                onChange={e => setLogLimit(Number(e.target.value))}
                className="px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white"
              >
                <option value={50}>50 lineas</option>
                <option value={100}>100 lineas</option>
                <option value={200}>200 lineas</option>
                <option value={500}>500 lineas</option>
              </select>
              <button
                onClick={fetchLogs}
                disabled={loadingLogs}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
              >
                {loadingLogs ? 'Cargando...' : 'Buscar'}
              </button>
            </div>

            {/* Log entries */}
            <div className="bg-gray-900 rounded-lg p-4 max-h-[600px] overflow-y-auto font-mono text-xs">
              {logs.length === 0 && (
                <div className="text-center py-8 text-gray-500">
                  <p className="text-2xl mb-2">🔍</p>
                  <p>Haz clic en "Buscar" para cargar los logs</p>
                </div>
              )}
              {logs.map((log, i) => (
                <div
                  key={i}
                  className={`flex items-start gap-2 py-1 px-2 rounded mb-0.5 ${
                    log.level === 'error' ? 'bg-red-950/50' :
                    log.level === 'warning' ? 'bg-yellow-950/30' : ''
                  }`}
                >
                  <span className={`inline-block w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${levelBadgeColors[log.level] || 'bg-gray-500'}`} />
                  <span className={`break-all ${
                    log.level === 'error' ? 'text-red-400' :
                    log.level === 'warning' ? 'text-yellow-400' : 'text-gray-300'
                  }`}>
                    {logSearch && log.message.toUpperCase().includes(logSearch.toUpperCase())
                      ? highlightText(log.message, logSearch)
                      : log.message
                    }
                  </span>
                </div>
              ))}
              <div ref={logsEndRef} />
            </div>

            {logs.length > 0 && (
              <div className="flex items-center justify-between mt-3 text-sm text-gray-500">
                <span>{logs.length} entradas</span>
                <span>
                  {logs.filter(l => l.level === 'error').length} errores |{' '}
                  {logs.filter(l => l.level === 'warning').length} warnings
                </span>
              </div>
            )}
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="text-center py-6 text-xs text-gray-400">
        Panel de Soporte - Onboarding Seguridad KOF - EnterSys
      </footer>
    </div>
  );
}
