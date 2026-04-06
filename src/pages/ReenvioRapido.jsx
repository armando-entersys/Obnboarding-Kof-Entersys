import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { config } from '@/config/environment';

const API_BASE_URL = config.urls.api;

export default function ReenvioRapido() {
  const { rfc: rfcParam } = useParams();
  const [rfcInput, setRfcInput] = useState('');
  const [status, setStatus] = useState(rfcParam ? 'loading' : 'form'); // form, loading, success, error
  const [data, setData] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [activeRfc, setActiveRfc] = useState(rfcParam || '');

  const doResend = async (rfc) => {
    setActiveRfc(rfc);
    setStatus('loading');
    setErrorMsg('');
    try {
      const resp = await fetch(`${API_BASE_URL}/v1/onboarding/quick-resend/${rfc.toUpperCase()}`, {
        method: 'POST',
      });
      const result = await resp.json();

      if (resp.ok && result.success) {
        setStatus('success');
        setData(result);
      } else {
        setStatus('error');
        setErrorMsg(result.detail || result.message || 'Error al reenviar');
      }
    } catch (e) {
      setStatus('error');
      setErrorMsg('Error de conexión con el servidor');
    }
  };

  useEffect(() => {
    if (rfcParam) doResend(rfcParam);
  }, [rfcParam]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (rfcInput.trim().length >= 10) {
      doResend(rfcInput.trim().toUpperCase());
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-6">
          <img src="/onboarding-assets/images/coca-cola-femsa-logo.png" alt="FEMSA" className="h-14 mx-auto mb-3" />
          <p className="text-sm text-gray-500">Onboarding Seguridad KOF</p>
        </div>

        <div className="bg-white rounded-lg shadow-lg p-8">
          {status === 'form' && (
            <form onSubmit={handleSubmit} className="space-y-5">
              <div className="text-center mb-2">
                <div className="w-14 h-14 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-3">
                  <span className="text-2xl">📧</span>
                </div>
                <h2 className="text-xl font-bold text-gray-800">Reenvío de Certificado</h2>
                <p className="text-sm text-gray-500 mt-1">Ingresa tu RFC para reenviar tu certificado al correo registrado</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">RFC del Colaborador</label>
                <input
                  type="text"
                  value={rfcInput}
                  onChange={e => setRfcInput(e.target.value.toUpperCase())}
                  placeholder="Ej: SAML970804196"
                  maxLength={13}
                  autoFocus
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 focus:border-red-500 font-mono uppercase text-center text-lg tracking-wider"
                />
              </div>
              <button
                type="submit"
                disabled={rfcInput.trim().length < 10}
                className="w-full py-3 bg-red-600 text-white rounded-lg font-medium hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Reenviar Certificado
              </button>
            </form>
          )}

          {status === 'loading' && (
            <div className="text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-red-600 mx-auto mb-4" />
              <h2 className="text-lg font-bold text-gray-800 mb-2">Reenviando certificado...</h2>
              <p className="text-sm text-gray-500">RFC: <span className="font-mono">{activeRfc.toUpperCase()}</span></p>
            </div>
          )}

          {status === 'success' && (
            <div className="text-center">
              <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <svg className="w-8 h-8 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h2 className="text-xl font-bold text-green-800 mb-3">Certificado reenviado</h2>
              <div className="bg-green-50 border border-green-200 rounded-lg p-4 text-left space-y-2">
                <p className="text-sm text-gray-700">
                  <span className="font-medium">Nombre:</span> {data?.nombre}
                </p>
                <p className="text-sm text-gray-700">
                  <span className="font-medium">RFC:</span> <span className="font-mono">{activeRfc.toUpperCase()}</span>
                </p>
                <p className="text-sm text-gray-700">
                  <span className="font-medium">Enviado a:</span> {data?.email_masked}
                </p>
              </div>
              <p className="text-xs text-gray-400 mt-4">Recibirás tu certificado, QR y PDF por correo.</p>
              <button
                onClick={() => { setStatus('form'); setRfcInput(''); }}
                className="mt-4 text-sm text-blue-600 hover:underline"
              >
                Reenviar otro certificado
              </button>
            </div>
          )}

          {status === 'error' && (
            <div className="text-center">
              <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <svg className="w-8 h-8 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
              <h2 className="text-xl font-bold text-red-800 mb-3">Error al reenviar</h2>
              <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                <p className="text-sm text-red-700">{errorMsg}</p>
                <p className="text-sm text-gray-500 mt-2">RFC: <span className="font-mono">{activeRfc.toUpperCase()}</span></p>
              </div>
              <button
                onClick={() => { setStatus('form'); setRfcInput(''); }}
                className="mt-4 text-sm text-blue-600 hover:underline"
              >
                Intentar de nuevo
              </button>
            </div>
          )}
        </div>

        <p className="text-center text-xs text-gray-400 mt-4">Onboarding Seguridad KOF - EnterSys</p>
      </div>
    </div>
  );
}
