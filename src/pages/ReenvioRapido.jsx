import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { config } from '@/config/environment';

const API_BASE_URL = config.urls.api;

export default function ReenvioRapido() {
  const { rfc } = useParams();
  const [status, setStatus] = useState('loading'); // loading, success, error
  const [data, setData] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    if (!rfc) return;

    const resend = async () => {
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

    resend();
  }, [rfc]);

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-6">
          <img src="/onboarding-assets/images/coca-cola-femsa-logo.png" alt="FEMSA" className="h-14 mx-auto mb-3" />
          <p className="text-sm text-gray-500">Onboarding Seguridad KOF</p>
        </div>

        <div className="bg-white rounded-lg shadow-lg p-8">
          {status === 'loading' && (
            <div className="text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-red-600 mx-auto mb-4" />
              <h2 className="text-lg font-bold text-gray-800 mb-2">Reenviando certificado...</h2>
              <p className="text-sm text-gray-500">RFC: <span className="font-mono">{rfc?.toUpperCase()}</span></p>
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
                  <span className="font-medium">RFC:</span> <span className="font-mono">{rfc?.toUpperCase()}</span>
                </p>
                <p className="text-sm text-gray-700">
                  <span className="font-medium">Enviado a:</span> {data?.email_masked}
                </p>
              </div>
              <p className="text-xs text-gray-400 mt-4">El colaborador recibirá su certificado, QR y PDF por correo.</p>
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
                <p className="text-sm text-gray-500 mt-2">RFC: <span className="font-mono">{rfc?.toUpperCase()}</span></p>
              </div>
            </div>
          )}
        </div>

        <p className="text-center text-xs text-gray-400 mt-4">Panel de Soporte - EnterSys</p>
      </div>
    </div>
  );
}
