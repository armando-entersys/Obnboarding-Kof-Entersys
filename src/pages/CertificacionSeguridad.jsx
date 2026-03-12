import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import { config } from '../config/environment';

const API_BASE_URL = config.urls.api;

/**
 * CertificacionSeguridad Page
 * Página dinámica que obtiene datos del certificado desde el API
 * Muestra: Aprobado, No Aprobado, Vencido o No Encontrado
 */
const CertificacionSeguridad = () => {
  const { uuid } = useParams();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [certificateData, setCertificateData] = useState(null);

  useEffect(() => {
    const fetchCertificateData = async () => {
      if (!uuid) {
        setError('UUID no proporcionado');
        setLoading(false);
        return;
      }

      try {
        const response = await fetch(`${API_BASE_URL}/v1/onboarding/certificate/${uuid}`);
        const data = await response.json();

        setCertificateData(data);
        setLoading(false);
      } catch (err) {
        console.error('Error fetching certificate:', err);
        setError('Error al conectar con el servidor');
        setLoading(false);
      }
    };

    fetchCertificateData();
  }, [uuid]);

  // Loading state
  if (loading) {
    return (
      <main className="min-h-screen flex flex-col bg-gradient-to-b from-gray-50 to-white">
        <header className="bg-white shadow-sm py-6">
          <div className="max-w-4xl mx-auto px-4 flex justify-center">
            <img src="/images/coca-cola-femsa-logo.png" alt="Coca-Cola FEMSA" className="h-20 md:h-24" />
          </div>
        </header>
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-[#FFC600] mx-auto mb-4"></div>
            <p className="text-gray-600">Validando certificado...</p>
          </div>
        </div>
      </main>
    );
  }

  // Error or not found state
  if (error || !certificateData?.success) {
    return (
      <>
        <Helmet>
          <title>Certificado No Encontrado | FEMSA</title>
          <meta name="robots" content="noindex, nofollow" />
        </Helmet>

        <main className="min-h-screen flex flex-col bg-gradient-to-b from-gray-50 to-white">
          <header className="bg-white shadow-sm py-6">
            <div className="max-w-4xl mx-auto px-4 flex justify-center">
              <img src="/images/coca-cola-femsa-logo.png" alt="Coca-Cola FEMSA" className="h-20 md:h-24" />
            </div>
          </header>

          <div className="flex-1 flex items-center justify-center px-4 py-12">
            <div className="max-w-2xl w-full text-center">
              <div className="mb-8">
                <div className="inline-flex items-center justify-center w-24 h-24 rounded-full bg-gray-100 mb-4">
                  <svg className="w-16 h-16 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <div className="h-1 w-24 bg-[#FFC600] mx-auto rounded"></div>
              </div>

              <h1 className="text-4xl font-bold text-gray-900 mb-6">Certificado No Encontrado</h1>

              <p className="text-lg text-gray-600 mb-8 max-w-xl mx-auto leading-relaxed">
                {error || certificateData?.message || 'No se pudo encontrar el certificado solicitado. Verifica que el código QR sea válido.'}
              </p>

              <p className="text-sm text-gray-500">
                Verificado el {new Date().toLocaleDateString('es-MX', {
                  day: '2-digit',
                  month: 'long',
                  year: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit'
                })}
              </p>
            </div>
          </div>

          <footer className="bg-gray-100 py-6">
            <div className="max-w-4xl mx-auto px-4 text-center">
              <p className="text-sm text-gray-600 mb-3">© {new Date().getFullYear()} Entersys. Todos los derechos reservados.</p>
              <div className="flex justify-center space-x-6 text-sm">
                <a href="https://www.entersys.mx/politica-de-privacidad" className="text-gray-500 hover:text-[#FFC600] transition-colors">Política de privacidad</a>
                <a href="https://www.entersys.mx/terminos-de-servicio" className="text-gray-500 hover:text-[#FFC600] transition-colors">Términos de servicio</a>
                <a href="https://www.entersys.mx/configuracion-de-cookies" className="text-gray-500 hover:text-[#FFC600] transition-colors">Configuración de cookies</a>
              </div>
            </div>
          </footer>
        </main>
      </>
    );
  }

  const { status, nombre, vencimiento, message, url_imagen } = certificateData;

  // Format expiration date for display
  const formatDate = (dateStr) => {
    if (!dateStr) return 'No disponible';

    // Try to parse and format
    const parts = dateStr.split('/');
    if (parts.length === 3) {
      const [day, month, year] = parts;
      const date = new Date(year, month - 1, day);
      if (!isNaN(date.getTime())) {
        return date.toLocaleDateString('es-MX', {
          day: '2-digit',
          month: 'long',
          year: 'numeric'
        });
      }
    }
    return dateStr;
  };

  const formattedExpiration = formatDate(vencimiento);

  // EXPIRED state
  if (status === 'expired') {
    return (
      <>
        <Helmet>
          <title>Onboarding Vencido - No Aprobado | FEMSA</title>
          <meta name="robots" content="noindex, nofollow" />
        </Helmet>

        <main className="min-h-screen flex flex-col bg-gradient-to-b from-gray-50 to-white">
          <header className="bg-white shadow-sm py-6">
            <div className="max-w-4xl mx-auto px-4 flex justify-center">
              <img src="/images/coca-cola-femsa-logo.png" alt="Coca-Cola FEMSA" className="h-20 md:h-24" />
            </div>
          </header>

          <div className="flex-1 flex items-center justify-center px-4 py-12">
            <div className="max-w-2xl w-full text-center">
              <div className="mb-8">
                <div className="inline-flex items-center justify-center w-24 h-24 rounded-full bg-red-100 mb-4">
                  <svg className="w-16 h-16 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <div className="h-1 w-24 bg-[#FFC600] mx-auto rounded"></div>
              </div>

              <h1 className="text-4xl font-bold text-gray-900 mb-6">Onboarding Vencido</h1>

              <div className="bg-white border border-gray-200 rounded-lg p-6 mb-6 shadow-sm">
                <p className="text-2xl font-semibold text-gray-900 mb-2">{nombre}</p>
                <p className="text-gray-600">Venció el: <span className="text-red-600 font-semibold">{formattedExpiration}</span></p>
              </div>

              <p className="text-lg text-gray-600 mb-6 max-w-xl mx-auto leading-relaxed">
                Tu certificación de Seguridad Industrial ha expirado y <strong>NO está autorizado para ingresar</strong> a las instalaciones.
              </p>

              <p className="text-base text-gray-600 mb-8 max-w-xl mx-auto leading-relaxed">
                Por favor contacta a tu supervisor para renovar tu certificación y completar nuevamente el proceso de onboarding.
              </p>

              <div className="inline-flex items-center px-6 py-3 rounded-full bg-red-100 text-red-800 font-semibold mb-8">
                <svg className="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
                No Aprobado para Ingresar
              </div>

              <p className="text-sm text-gray-500">
                Verificado el {new Date().toLocaleDateString('es-MX', {
                  day: '2-digit',
                  month: 'long',
                  year: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit'
                })}
              </p>
            </div>
          </div>

          <footer className="bg-gray-100 py-6">
            <div className="max-w-4xl mx-auto px-4 text-center">
              <p className="text-sm text-gray-600 mb-3">© {new Date().getFullYear()} Entersys. Todos los derechos reservados.</p>
              <div className="flex justify-center space-x-6 text-sm">
                <a href="https://www.entersys.mx/politica-de-privacidad" className="text-gray-500 hover:text-[#FFC600] transition-colors">Política de privacidad</a>
                <a href="https://www.entersys.mx/terminos-de-servicio" className="text-gray-500 hover:text-[#FFC600] transition-colors">Términos de servicio</a>
                <a href="https://www.entersys.mx/configuracion-de-cookies" className="text-gray-500 hover:text-[#FFC600] transition-colors">Configuración de cookies</a>
              </div>
            </div>
          </footer>
        </main>
      </>
    );
  }

  // NOT APPROVED state (score < 80)
  if (status === 'not_approved') {
    return (
      <>
        <Helmet>
          <title>Onboarding No Aprobado | FEMSA</title>
          <meta name="robots" content="noindex, nofollow" />
        </Helmet>

        <main className="min-h-screen flex flex-col bg-gradient-to-b from-gray-50 to-white">
          <header className="bg-white shadow-sm py-6">
            <div className="max-w-4xl mx-auto px-4 flex justify-center">
              <img src="/images/coca-cola-femsa-logo.png" alt="Coca-Cola FEMSA" className="h-20 md:h-24" />
            </div>
          </header>

          <div className="flex-1 flex items-center justify-center px-4 py-12">
            <div className="max-w-2xl w-full text-center">
              <div className="mb-8">
                <div className="inline-flex items-center justify-center w-24 h-24 rounded-full bg-red-100 mb-4">
                  <svg className="w-16 h-16 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                </div>
                <div className="h-1 w-24 bg-[#FFC600] mx-auto rounded"></div>
              </div>

              <h1 className="text-4xl font-bold text-gray-900 mb-6">Onboarding No Aprobado</h1>

              <div className="bg-white border border-gray-200 rounded-lg p-6 mb-6 shadow-sm">
                <p className="text-2xl font-semibold text-gray-900 mb-2">{nombre}</p>
                {vencimiento && (
                  <p className="text-gray-600">Vigencia: <span className="text-red-600 font-semibold">{formattedExpiration}</span></p>
                )}
              </div>

              <p className="text-lg text-gray-600 mb-6 max-w-xl mx-auto leading-relaxed">
                Tu certificación de Seguridad Industrial no pudo ser validada.
                La información proporcionada o los requisitos del curso no cumplen
                con los estándares mínimos de seguridad establecidos.
              </p>

              <p className="text-base text-gray-600 mb-8 max-w-xl mx-auto leading-relaxed">
                Por favor revisa las observaciones enviadas, corrige la información
                o completa los requisitos faltantes para volver a enviar tu solicitud
                de validación.
              </p>

              <div className="inline-flex items-center px-6 py-3 rounded-full bg-red-100 text-red-800 font-semibold mb-8">
                <svg className="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
                Certificación No Válida
              </div>

              <p className="text-sm text-gray-500">
                Verificado el {new Date().toLocaleDateString('es-MX', {
                  day: '2-digit',
                  month: 'long',
                  year: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit'
                })}
              </p>
            </div>
          </div>

          <footer className="bg-gray-100 py-6">
            <div className="max-w-4xl mx-auto px-4 text-center">
              <p className="text-sm text-gray-600 mb-3">© {new Date().getFullYear()} Entersys. Todos los derechos reservados.</p>
              <div className="flex justify-center space-x-6 text-sm">
                <a href="https://www.entersys.mx/politica-de-privacidad" className="text-gray-500 hover:text-[#FFC600] transition-colors">Política de privacidad</a>
                <a href="https://www.entersys.mx/terminos-de-servicio" className="text-gray-500 hover:text-[#FFC600] transition-colors">Términos de servicio</a>
                <a href="https://www.entersys.mx/configuracion-de-cookies" className="text-gray-500 hover:text-[#FFC600] transition-colors">Configuración de cookies</a>
              </div>
            </div>
          </footer>
        </main>
      </>
    );
  }

  // APPROVED state (score >= 80 and not expired)
  return (
    <>
      <Helmet>
        <title>Onboarding Aprobado | FEMSA</title>
        <meta name="description" content="Tu certificación de Seguridad Industrial ha sido validada correctamente." />
        <meta name="robots" content="noindex, nofollow" />
      </Helmet>

      <main className="min-h-screen flex flex-col bg-gradient-to-b from-gray-50 to-white">
        <header className="bg-white shadow-sm py-6">
          <div className="max-w-4xl mx-auto px-4 flex justify-center">
            <img src="/images/coca-cola-femsa-logo.png" alt="Coca-Cola FEMSA" className="h-20 md:h-24" />
          </div>
        </header>

        <div className="flex-1 flex items-center justify-center px-4 py-12">
          <div className="max-w-2xl w-full text-center">
            <div className="mb-8">
              <div className="inline-flex items-center justify-center w-24 h-24 rounded-full bg-green-100 mb-4">
                <svg className="w-16 h-16 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div className="h-1 w-24 bg-[#FFC600] mx-auto rounded"></div>
            </div>

            <h1 className="text-4xl font-bold text-gray-900 mb-6">Onboarding Aprobado</h1>

            <div className="bg-white border border-gray-200 rounded-lg p-6 mb-6 shadow-sm">
              {/* Foto de credencial */}
              {url_imagen && (
                <div className="mb-4 flex justify-center">
                  <img
                    src={url_imagen}
                    alt={`Foto de ${nombre}`}
                    className="w-32 h-40 object-cover rounded-lg border-2 border-gray-200 shadow-md"
                  />
                </div>
              )}
              <p className="text-2xl font-semibold text-gray-900 mb-2">{nombre}</p>
              <p className="text-gray-600">Vigencia hasta: <span className="text-green-600 font-semibold">{formattedExpiration}</span></p>
            </div>

            <p className="text-lg text-gray-600 mb-8 max-w-xl mx-auto leading-relaxed">
              Tu certificación de Seguridad Industrial ha sido validada correctamente.
              Has cumplido con todos los requisitos del curso y tu información ha sido
              aprobada conforme a los estándares de seguridad establecidos.
            </p>

            <div className="inline-flex items-center px-6 py-3 rounded-full bg-green-100 text-green-800 font-semibold mb-8">
              <svg className="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              Certificación Válida
            </div>

            <p className="text-sm text-gray-500">
              Verificado el {new Date().toLocaleDateString('es-MX', {
                day: '2-digit',
                month: 'long',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
              })}
            </p>
          </div>
        </div>

        <footer className="bg-gray-100 py-6">
          <div className="max-w-4xl mx-auto px-4 text-center">
            <p className="text-sm text-gray-600 mb-3">© {new Date().getFullYear()} Entersys. Todos los derechos reservados.</p>
            <div className="flex justify-center space-x-6 text-sm">
              <a href="https://www.entersys.mx/politica-de-privacidad" className="text-gray-500 hover:text-[#FFC600] transition-colors">Política de privacidad</a>
              <a href="https://www.entersys.mx/terminos-de-servicio" className="text-gray-500 hover:text-[#FFC600] transition-colors">Términos de servicio</a>
              <a href="https://www.entersys.mx/configuracion-de-cookies" className="text-gray-500 hover:text-[#FFC600] transition-colors">Configuración de cookies</a>
            </div>
          </div>
        </footer>
      </main>
    </>
  );
};

export default CertificacionSeguridad;
