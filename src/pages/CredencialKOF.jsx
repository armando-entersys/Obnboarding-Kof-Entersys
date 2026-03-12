/**
 * CredencialKOF Page
 * Credencial Digital Inteligente y Pasaporte de Seguridad (KOF)
 *
 * Muestra credencial con 2 niveles:
 * - Bajo/Medio Riesgo: Foto, nombre, edad, estatus onboarding
 * - Alto Riesgo: Todo lo anterior + ficha técnica extendida (legales, competencias, historial)
 */

import React, { useState, useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import { QRCodeSVG } from 'qrcode.react';
import { BiLogoFacebookCircle, BiLogoInstagram, BiLogoLinkedinSquare, BiLogoYoutube } from 'react-icons/bi';
import { config } from '../config/environment';

const API_BASE_URL = config.urls.api;

const CredencialKOF = () => {
  const { rfc } = useParams();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [credentialData, setCredentialData] = useState(null);
  const [showFichaTecnica, setShowFichaTecnica] = useState(false);

  useEffect(() => {
    const fetchCredentialData = async () => {
      if (!rfc) {
        setError('RFC no proporcionado');
        setLoading(false);
        return;
      }

      try {
        const response = await fetch(`${API_BASE_URL}/v1/onboarding/credential/${rfc}`);
        const data = await response.json();
        setCredentialData(data);
        setLoading(false);
      } catch (err) {
        console.error('Error fetching credential:', err);
        setError('Error al conectar con el servidor');
        setLoading(false);
      }
    };

    fetchCredentialData();
  }, [rfc]);

  const formatDate = (dateStr) => {
    if (!dateStr) return 'No disponible';
    let date;
    if (dateStr.includes('-')) {
      const parts = dateStr.split('-');
      if (parts.length === 3) date = new Date(parts[0], parts[1] - 1, parts[2]);
    } else if (dateStr.includes('/')) {
      const parts = dateStr.split('/');
      if (parts.length === 3) date = new Date(parts[2], parts[1] - 1, parts[0]);
    }
    if (date && !isNaN(date.getTime())) {
      return date.toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: 'numeric' });
    }
    return dateStr;
  };

  const getCertificateUrl = (uuid) => {
    if (!uuid) return null;
    return `https://entersys.mx/certificacion-seguridad/${uuid}`;
  };

  // Loading
  if (loading) {
    return (
      <main className="min-h-screen flex flex-col bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900">
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-[#FFC600] mx-auto mb-4"></div>
            <p className="text-gray-300">Cargando credencial...</p>
          </div>
        </div>
      </main>
    );
  }

  // Error / Not found
  if (error || !credentialData?.success) {
    return (
      <>
        <Helmet>
          <title>Credencial No Encontrada | FEMSA</title>
          <meta name="robots" content="noindex, nofollow" />
        </Helmet>
        <main className="min-h-screen flex flex-col bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900">
          <header className="py-6">
            <div className="max-w-4xl mx-auto px-4 flex justify-center">
              <img src="/images/coca-cola-femsa-logo.png" alt="Coca-Cola FEMSA" className="h-16 md:h-20" />
            </div>
          </header>
          <div className="flex-1 flex items-center justify-center px-4 py-12">
            <div className="max-w-md w-full text-center">
              <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-8 border border-white/20">
                <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-red-500/20 mb-6">
                  <svg className="w-10 h-10 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                </div>
                <h1 className="text-2xl font-bold text-white mb-4">Credencial No Encontrada</h1>
                <p className="text-gray-300 mb-2">RFC: <span className="font-mono text-[#FFC600]">{rfc?.toUpperCase()}</span></p>
                <p className="text-gray-400 text-sm">
                  {error || credentialData?.message || 'No se encontró registro para este RFC.'}
                </p>
              </div>
            </div>
          </div>
          <Footer />
        </main>
      </>
    );
  }

  const {
    status, nombre, proveedor, tipo_servicio, nss, rfc_empresa,
    cert_uuid, vencimiento, fecha_emision, url_imagen, is_expired,
    alto_riesgo, edad, alto_riesgo_data,
  } = credentialData;

  const certificateUrl = getCertificateUrl(cert_uuid);
  const photoUrl = url_imagen || '/images/credential-photo.jpg';
  const fichaTecnicaUrl = alto_riesgo && nss
    ? `https://entersys.mx/credencial-kof/${rfc}/ficha-tecnica`
    : null;

  const getStatusConfig = () => {
    if (status === 'approved') {
      return {
        label: 'VIGENTE',
        bgColor: 'bg-green-500',
        textColor: 'text-green-500',
        borderColor: 'border-green-500',
        icon: (
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
          </svg>
        )
      };
    } else if (status === 'expired') {
      return {
        label: 'VENCIDA',
        bgColor: 'bg-orange-500',
        textColor: 'text-orange-500',
        borderColor: 'border-orange-500',
        icon: (
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
          </svg>
        )
      };
    }
    return {
      label: 'NO VÁLIDA',
      bgColor: 'bg-red-500',
      textColor: 'text-red-500',
      borderColor: 'border-red-500',
      icon: (
        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
        </svg>
      )
    };
  };

  const statusConfig = getStatusConfig();

  return (
    <>
      <Helmet>
        <title>Credencial Virtual - {nombre} | FEMSA</title>
        <meta name="robots" content="noindex, nofollow" />
      </Helmet>

      <main className="min-h-screen flex flex-col bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900">
        {/* Header */}
        <header className="py-6">
          <div className="max-w-4xl mx-auto px-4 flex justify-center">
            <img src="/images/coca-cola-femsa-logo.png" alt="Coca-Cola FEMSA" className="h-16 md:h-20" />
          </div>
        </header>

        {/* Credential Card */}
        <div className="flex-1 flex items-center justify-center px-4 py-8">
          <div className="w-full max-w-md">
            <div className="relative">
              {/* Glow */}
              <div className={`absolute inset-0 ${statusConfig.bgColor} opacity-20 blur-xl rounded-3xl`}></div>

              {/* Main Card */}
              <div className={`relative bg-gradient-to-br from-gray-800 to-gray-900 rounded-3xl overflow-hidden border-2 ${statusConfig.borderColor} shadow-2xl`}>
                {/* Top Banner */}
                <div className="bg-gradient-to-r from-red-600 to-red-700 px-6 py-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-white/80 text-xs uppercase tracking-wider">Credencial de Seguridad</p>
                      <p className="text-white font-bold text-lg">ONBOARDING KOF</p>
                    </div>
                    <div className={`${statusConfig.bgColor} text-white px-3 py-1 rounded-full text-xs font-bold flex items-center gap-1`}>
                      {statusConfig.icon}
                      {statusConfig.label}
                    </div>
                  </div>
                </div>

                {/* Card Body */}
                <div className="p-6">
                  {/* Photo and Info */}
                  <div className="flex gap-6">
                    <div className="flex-shrink-0">
                      <div className="w-24 h-28 bg-gray-700 rounded-lg overflow-hidden border-2 border-gray-600 shadow-lg">
                        <img
                          src={photoUrl}
                          alt={`Foto de ${nombre}`}
                          className="w-full h-full object-cover"
                          onError={(e) => {
                            e.target.style.display = 'none';
                            e.target.parentElement.innerHTML = `
                              <div class="w-full h-full flex items-center justify-center bg-gray-700">
                                <svg class="w-12 h-12 text-gray-500" fill="currentColor" viewBox="0 0 24 24">
                                  <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
                                </svg>
                              </div>
                            `;
                          }}
                        />
                      </div>
                    </div>

                    <div className="flex-1 min-w-0">
                      <h2 className="text-white font-bold text-xl mb-1 truncate">{nombre}</h2>
                      {edad && (
                        <p className="text-gray-400 text-sm mb-1">{edad} años</p>
                      )}
                      <p className="text-[#FFC600] font-mono text-sm mb-3">{rfc?.toUpperCase()}</p>

                      {proveedor && (
                        <div className="mb-2">
                          <p className="text-gray-500 text-xs uppercase tracking-wide">Empresa</p>
                          <p className="text-gray-300 text-sm truncate">{proveedor}</p>
                        </div>
                      )}

                      {tipo_servicio && (
                        <div>
                          <p className="text-gray-500 text-xs uppercase tracking-wide">Servicio</p>
                          <p className="text-gray-300 text-sm truncate">{tipo_servicio}</p>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Estatus Onboarding */}
                  <div className="mt-4 bg-gray-800/50 rounded-lg p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-gray-400 text-xs uppercase tracking-wide">Estatus Onboarding</span>
                      <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                        status === 'approved' ? 'bg-green-500/20 text-green-400' :
                        status === 'expired' ? 'bg-orange-500/20 text-orange-400' :
                        'bg-red-500/20 text-red-400'
                      }`}>
                        {status === 'approved' ? 'APROBADO' : status === 'expired' ? 'EXPIRADO' : 'NO APROBADO'}
                      </span>
                    </div>
                  </div>

                  {/* Indicador Alto Riesgo */}
                  <div className="mt-3 bg-gray-800/50 rounded-lg p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-gray-400 text-xs uppercase tracking-wide">Registrado para Alto Riesgo</span>
                      {alto_riesgo ? (
                        <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-400 flex items-center gap-1">
                          <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                          </svg>
                          SI
                        </span>
                      ) : (
                        <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-gray-600/30 text-gray-500">
                          NO
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Unidad Operativa / Actividad (solo alto riesgo) */}
                  {alto_riesgo && alto_riesgo_data && (
                    <div className="mt-3 bg-gray-800/50 rounded-lg p-3">
                      <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">Actividad / Cargo</p>
                      <p className="text-gray-200 text-sm">{alto_riesgo_data.cargo || 'Sin asignar'}</p>
                      {alto_riesgo_data.funciones && (
                        <p className="text-gray-400 text-xs mt-1">{alto_riesgo_data.funciones}</p>
                      )}
                    </div>
                  )}

                  {/* NSS y RFC Empresa */}
                  {(nss || rfc_empresa) && (
                    <div className="mt-4 grid grid-cols-2 gap-4">
                      {nss && (
                        <div>
                          <p className="text-gray-500 text-xs uppercase tracking-wide">NSS</p>
                          <p className="text-gray-300 text-sm font-mono">{nss}</p>
                        </div>
                      )}
                      {rfc_empresa && (
                        <div>
                          <p className="text-gray-500 text-xs uppercase tracking-wide">RFC Empresa</p>
                          <p className="text-gray-300 text-sm font-mono">{rfc_empresa}</p>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Divider */}
                  <div className="my-6 border-t border-gray-700 border-dashed"></div>

                  {/* QR and Dates */}
                  <div className="flex gap-6">
                    <div className="flex-shrink-0">
                      {certificateUrl ? (
                        <div className="bg-white p-2 rounded-lg">
                          <QRCodeSVG
                            value={alto_riesgo ? (fichaTecnicaUrl || certificateUrl) : certificateUrl}
                            size={100}
                            level="M"
                            includeMargin={false}
                          />
                        </div>
                      ) : (
                        <div className="w-[116px] h-[116px] bg-gray-700 rounded-lg flex items-center justify-center">
                          <p className="text-gray-500 text-xs text-center px-2">Sin QR disponible</p>
                        </div>
                      )}
                    </div>

                    <div className="flex-1 flex flex-col justify-center">
                      {fecha_emision && (
                        <div className="mb-3">
                          <p className="text-gray-500 text-xs uppercase tracking-wide">Emisión</p>
                          <p className="text-gray-300 text-sm">{formatDate(fecha_emision)}</p>
                        </div>
                      )}

                      {vencimiento && (
                        <div className="mb-3">
                          <p className="text-gray-500 text-xs uppercase tracking-wide">Vigencia</p>
                          <p className={`text-sm font-semibold ${is_expired ? 'text-orange-400' : 'text-green-400'}`}>
                            {formatDate(vencimiento)}
                          </p>
                        </div>
                      )}

                      {certificateUrl && (
                        <a
                          href={certificateUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-[#FFC600] text-xs hover:underline"
                        >
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                          </svg>
                          Ver certificación
                        </a>
                      )}
                    </div>
                  </div>
                </div>

                {/* Bottom Banner */}
                <div className="bg-gray-800/50 px-6 py-3 border-t border-gray-700">
                  <div className="flex items-center justify-between">
                    <p className="text-gray-500 text-xs">
                      {alto_riesgo ? 'Escanea el QR para ver ficha técnica' : 'Escanea el QR para verificar'}
                    </p>
                    <img src="/images/logo-entersys-white.svg" alt="Entersys" className="h-5 opacity-50" onError={(e) => e.target.style.display = 'none'} />
                  </div>
                </div>
              </div>
            </div>

            {/* Boton Ficha Tecnica (solo alto riesgo) */}
            {alto_riesgo && alto_riesgo_data && (
              <div className="mt-6">
                <button
                  onClick={() => setShowFichaTecnica(!showFichaTecnica)}
                  className="w-full py-3 px-4 bg-amber-500/20 border border-amber-500/40 rounded-xl text-amber-400 font-semibold text-sm hover:bg-amber-500/30 transition-colors flex items-center justify-center gap-2"
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  {showFichaTecnica ? 'Ocultar Ficha Técnica' : 'Ver Ficha Técnica de Alto Riesgo'}
                  <svg className={`w-4 h-4 transition-transform ${showFichaTecnica ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                {/* Ficha Tecnica Extendida */}
                {showFichaTecnica && (
                  <div className="mt-4 space-y-4 animate-fadeIn">
                    {/* Legales */}
                    <div className="bg-white/5 backdrop-blur rounded-xl p-4 border border-white/10">
                      <h3 className="text-amber-400 font-bold text-sm uppercase tracking-wide mb-3 flex items-center gap-2">
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3" />
                        </svg>
                        Datos Legales
                      </h3>
                      <div className="grid grid-cols-2 gap-3">
                        <InfoField label="NSS" value={alto_riesgo_data.nss} mono />
                        <InfoField label="RFC Empresa" value={alto_riesgo_data.rfc_empresa} mono />
                        <InfoField label="Cargo" value={alto_riesgo_data.cargo} />
                        <InfoField label="Validación de Cargo" value={alto_riesgo_data.validacion_cargo} highlight={alto_riesgo_data.validacion_cargo?.toLowerCase().includes('no apto')} />
                        <InfoField label="Edad" value={alto_riesgo_data.edad ? `${alto_riesgo_data.edad} años` : null} />
                        <InfoField label="Empresa" value={alto_riesgo_data.empresa_contratista} />
                      </div>
                      {alto_riesgo_data.validacion_cargo?.toLowerCase().includes('no apto') && (
                        <div className="mt-3 bg-red-500/10 border border-red-500/30 rounded-lg p-2">
                          <p className="text-red-400 text-xs">No apto por edad para este cargo</p>
                        </div>
                      )}
                    </div>

                    {/* Competencias */}
                    <div className="bg-white/5 backdrop-blur rounded-xl p-4 border border-white/10">
                      <h3 className="text-amber-400 font-bold text-sm uppercase tracking-wide mb-3 flex items-center gap-2">
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
                        </svg>
                        Competencias
                      </h3>
                      <div className="space-y-3">
                        <div>
                          <p className="text-gray-500 text-xs uppercase tracking-wide mb-1">Trabajos Permitidos</p>
                          {alto_riesgo_data.trabajos_permitidos ? (
                            <div className="flex flex-wrap gap-1.5">
                              {alto_riesgo_data.trabajos_permitidos.split(',').map((t, i) => (
                                <span key={i} className="inline-block bg-amber-500/15 text-amber-300 text-xs px-2 py-0.5 rounded-full border border-amber-500/30">
                                  {t.trim()}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <p className="text-gray-500 text-sm">No especificados</p>
                          )}
                        </div>
                        {alto_riesgo_data.funciones && (
                          <div>
                            <p className="text-gray-500 text-xs uppercase tracking-wide mb-1">Funciones</p>
                            <p className="text-gray-300 text-sm">{alto_riesgo_data.funciones}</p>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Historial de Desempeno */}
                    <div className="bg-white/5 backdrop-blur rounded-xl p-4 border border-white/10">
                      <h3 className="text-amber-400 font-bold text-sm uppercase tracking-wide mb-3 flex items-center gap-2">
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                        </svg>
                        Historial de Desempeño
                      </h3>
                      <div className="grid grid-cols-3 gap-3">
                        <ProjectStat
                          label="Ejecutados"
                          value={alto_riesgo_data.proyectos_ejecutados}
                          color="text-green-400"
                          bgColor="bg-green-500/10"
                        />
                        <ProjectStat
                          label="En Ejecución"
                          value={alto_riesgo_data.proyectos_en_ejecucion}
                          color="text-blue-400"
                          bgColor="bg-blue-500/10"
                        />
                        <ProjectStat
                          label="Programados"
                          value={alto_riesgo_data.proyectos_programados}
                          color="text-purple-400"
                          bgColor="bg-purple-500/10"
                        />
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Action Messages */}
            {status === 'approved' && (
              <div className="mt-6 text-center">
                <p className="text-gray-400 text-sm mb-4">
                  Presenta esta credencial digital para acceder a las instalaciones
                </p>
              </div>
            )}

            {status === 'expired' && (
              <div className="mt-6 text-center">
                <div className="bg-orange-500/10 border border-orange-500/30 rounded-lg p-4">
                  <p className="text-orange-400 text-sm">
                    Tu certificación ha vencido. Contacta a tu supervisor para renovarla.
                  </p>
                </div>
              </div>
            )}

            {status === 'not_approved' && (
              <div className="mt-6 text-center">
                <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
                  <p className="text-red-400 text-sm">
                    No tienes una certificación de seguridad aprobada.
                  </p>
                  <Link
                    to="/curso-seguridad"
                    className="inline-block mt-3 px-4 py-2 bg-[#FFC600] text-gray-900 font-semibold rounded-lg hover:bg-[#FFD84D] transition-colors"
                  >
                    Realizar Curso
                  </Link>
                </div>
              </div>
            )}
          </div>
        </div>

        <Footer />
      </main>
    </>
  );
};

// Componente auxiliar para campos de informacion
const InfoField = ({ label, value, mono = false, highlight = false }) => (
  <div>
    <p className="text-gray-500 text-xs uppercase tracking-wide">{label}</p>
    <p className={`text-sm ${highlight ? 'text-red-400 font-semibold' : 'text-gray-300'} ${mono ? 'font-mono' : ''}`}>
      {value || 'N/A'}
    </p>
  </div>
);

// Componente auxiliar para estadisticas de proyectos
const ProjectStat = ({ label, value, color, bgColor }) => (
  <div className={`${bgColor} rounded-lg p-3 text-center`}>
    <p className={`text-2xl font-bold ${color}`}>{value || '0'}</p>
    <p className="text-gray-400 text-xs mt-1">{label}</p>
  </div>
);

// Footer
const Footer = () => (
  <footer className="bg-gray-900/50 py-6 border-t border-gray-800">
    <div className="max-w-4xl mx-auto px-4 text-center">
      <div className="flex justify-center space-x-4 mb-4">
        <a href={config.social.facebook} target="_blank" rel="noopener noreferrer" aria-label="Facebook" className="text-gray-500 hover:text-[#FFC600] transition-colors">
          <BiLogoFacebookCircle className="size-6" />
        </a>
        <a href={config.social.instagram} target="_blank" rel="noopener noreferrer" aria-label="Instagram" className="text-gray-500 hover:text-[#FFC600] transition-colors">
          <BiLogoInstagram className="size-6" />
        </a>
        <a href={config.social.linkedin} target="_blank" rel="noopener noreferrer" aria-label="LinkedIn" className="text-gray-500 hover:text-[#FFC600] transition-colors">
          <BiLogoLinkedinSquare className="size-6" />
        </a>
        <a href={config.social.youtube} target="_blank" rel="noopener noreferrer" aria-label="YouTube" className="text-gray-500 hover:text-[#FFC600] transition-colors">
          <BiLogoYoutube className="size-6" />
        </a>
      </div>
      <p className="text-sm text-gray-600 mb-3">&copy; {new Date().getFullYear()} Entersys. Todos los derechos reservados.</p>
      <div className="flex justify-center space-x-6 text-sm">
        <a href="https://www.entersys.mx/politica-de-privacidad" className="text-gray-500 hover:text-[#FFC600] transition-colors">Política de privacidad</a>
        <a href="https://www.entersys.mx/terminos-de-servicio" className="text-gray-500 hover:text-[#FFC600] transition-colors">Términos de servicio</a>
      </div>
    </div>
  </footer>
);

export default CredencialKOF;
