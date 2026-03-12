import React, { useState, useRef, useCallback, useEffect } from 'react';
import { BiLogoFacebookCircle, BiLogoInstagram, BiLogoLinkedinSquare, BiLogoYoutube } from 'react-icons/bi';
import { config } from '@/config/environment';
import toastService from '@/services/toast';

const API_BASE_URL = config.urls.api;

export default function ActualizarPerfil() {
  // Step control: 1 = verify, 2 = edit profile
  const [currentStep, setCurrentStep] = useState(1);

  // Step 1 state
  const [rfc, setRfc] = useState('');
  const [nss, setNss] = useState('');
  const [verifyErrors, setVerifyErrors] = useState({});
  const [isVerifying, setIsVerifying] = useState(false);

  // Step 2 state - profile data
  const [profileData, setProfileData] = useState(null);
  const [editData, setEditData] = useState({
    nombre: '',
    rfc_colaborador: '',
    rfc_empresa: '',
    email: '',
    nss: '',
    proveedor: '',
    tipo_servicio: '',
  });
  const [editErrors, setEditErrors] = useState({});
  const [isSaving, setIsSaving] = useState(false);

  // Camera state
  const [isCameraActive, setIsCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState(null);
  const [photoFile, setPhotoFile] = useState(null);
  const [photoPreview, setPhotoPreview] = useState(null);
  const [isUploadingPhoto, setIsUploadingPhoto] = useState(false);
  const [newPhotoUrl, setNewPhotoUrl] = useState(null);

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);

  const isMobile = useCallback(() => {
    return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
  }, []);

  // Cleanup camera on unmount
  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }
    };
  }, []);

  // ========== STEP 1: Verification ==========

  const validateVerifyForm = () => {
    const errors = {};
    const rfcVal = rfc.trim().toUpperCase();
    if (!rfcVal) {
      errors.rfc = 'El RFC es requerido';
    } else if (rfcVal.length < 12 || rfcVal.length > 13) {
      errors.rfc = 'El RFC debe tener 12 o 13 caracteres';
    } else if (!/^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{2,3}$/i.test(rfcVal)) {
      errors.rfc = 'Formato de RFC inválido';
    }

    const nssVal = nss.trim();
    if (!nssVal) {
      errors.nss = 'El NSS es requerido';
    } else if (!/^\d{11}$/.test(nssVal)) {
      errors.nss = 'El NSS debe tener exactamente 11 dígitos';
    }

    setVerifyErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleVerify = async () => {
    if (!validateVerifyForm()) return;

    setIsVerifying(true);
    try {
      const response = await fetch(`${API_BASE_URL}/v1/onboarding/profile/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          rfc: rfc.trim().toUpperCase(),
          nss: nss.trim(),
        }),
      });

      if (response.status === 401) {
        setVerifyErrors({ general: 'Datos incorrectos. Verifica tu RFC y NSS.' });
        return;
      }

      if (!response.ok) {
        throw new Error('Error del servidor');
      }

      const data = await response.json();
      setProfileData(data);
      setEditData({
        nombre: data.nombre || '',
        rfc_colaborador: data.rfc || '',
        rfc_empresa: data.rfc_empresa || '',
        email: data.email || '',
        nss: data.nss || '',
        proveedor: data.proveedor || '',
        tipo_servicio: data.tipo_servicio || '',
      });
      setCurrentStep(2);
      toastService.success('Identidad verificada correctamente');
    } catch (error) {
      console.error('Error verificando perfil:', error);
      setVerifyErrors({ general: 'Error al verificar. Intenta de nuevo.' });
    } finally {
      setIsVerifying(false);
    }
  };

  // ========== CAMERA ==========

  const startCamera = useCallback(async () => {
    setCameraError(null);

    try {
      let permState = 'unknown';
      try {
        if (navigator.permissions && navigator.permissions.query) {
          permState = (await navigator.permissions.query({ name: 'camera' })).state;
        }
      } catch {
        permState = 'query-not-supported';
      }

      if (permState === 'denied') {
        setCameraError('El permiso de cámara está bloqueado. Habilítalo en la configuración del navegador.');
        return;
      }

      const constraints = {
        video: {
          facingMode: 'user',
          width: { ideal: isMobile() ? 480 : 640 },
          height: { ideal: isMobile() ? 640 : 800 },
        },
        audio: false,
      };

      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      streamRef.current = stream;
      setIsCameraActive(true);

      setTimeout(() => {
        if (videoRef.current && streamRef.current) {
          videoRef.current.srcObject = streamRef.current;
          videoRef.current.play().catch(() => {});
        }
      }, 100);
    } catch (err) {
      if (err.name === 'OverconstrainedError' || err.name === 'ConstraintNotSatisfiedError') {
        try {
          const fallbackStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
          streamRef.current = fallbackStream;
          setIsCameraActive(true);
          setTimeout(() => {
            if (videoRef.current && streamRef.current) {
              videoRef.current.srcObject = streamRef.current;
              videoRef.current.play().catch(() => {});
            }
          }, 100);
          return;
        } catch {
          // continue to error handling
        }
      }

      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        setCameraError('Permiso de cámara denegado. Habilítalo en la configuración del navegador.');
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        setCameraError('No se encontró ninguna cámara en tu dispositivo.');
      } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
        setCameraError('La cámara está ocupada. Cierra otras apps que la usen.');
      } else {
        setCameraError(`Error al acceder a la cámara: ${err.message || 'Intenta recargar la página'}`);
      }
    }
  }, [isMobile]);

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setIsCameraActive(false);
  }, []);

  const capturePhoto = useCallback(() => {
    if (!videoRef.current || !canvasRef.current) return;

    const video = videoRef.current;
    const canvas = canvasRef.current;

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const ctx = canvas.getContext('2d');
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(video, 0, 0);

    canvas.toBlob((blob) => {
      if (blob) {
        const file = new File([blob], `foto_${Date.now()}.jpg`, { type: 'image/jpeg' });
        setPhotoFile(file);
        setPhotoPreview(canvas.toDataURL('image/jpeg', 0.9));
        stopCamera();
      }
    }, 'image/jpeg', 0.9);
  }, [stopCamera]);

  const removeNewPhoto = () => {
    setPhotoFile(null);
    setPhotoPreview(null);
    setNewPhotoUrl(null);
  };

  // Upload photo to GCS
  const uploadPhoto = async () => {
    if (!photoFile || !profileData?.rfc) return null;

    setIsUploadingPhoto(true);
    try {
      const formDataUpload = new FormData();
      formDataUpload.append('file', photoFile);
      formDataUpload.append('rfc', profileData.rfc.toUpperCase());

      const response = await fetch(`${API_BASE_URL}/v1/onboarding/upload-photo`, {
        method: 'POST',
        body: formDataUpload,
      });

      if (!response.ok) {
        throw new Error('Error al subir la foto');
      }

      const data = await response.json();
      return data.url;
    } catch (error) {
      console.error('Error subiendo foto:', error);
      toastService.error('Error al subir la foto. Intenta de nuevo.');
      return null;
    } finally {
      setIsUploadingPhoto(false);
    }
  };

  // ========== STEP 2: Edit & Save ==========

  const handleEditChange = (field, value) => {
    setEditData(prev => ({ ...prev, [field]: value }));
    if (editErrors[field]) {
      setEditErrors(prev => ({ ...prev, [field]: null }));
    }
  };

  const validateEditForm = () => {
    const errors = {};

    if (editData.nombre && !/^[\p{L}\s]+$/u.test(editData.nombre)) {
      errors.nombre = 'El nombre solo puede contener letras y espacios';
    }

    // RFC colaborador y NSS NO son editables, por lo tanto no se validan

    if (editData.rfc_empresa) {
      const rfcVal = editData.rfc_empresa.trim().toUpperCase();
      if (rfcVal.length < 12 || rfcVal.length > 13) {
        errors.rfc_empresa = 'El RFC debe tener 12 o 13 caracteres';
      } else if (!/^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{2,3}$/i.test(rfcVal)) {
        errors.rfc_empresa = 'Formato de RFC inválido';
      }
    }

    if (editData.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(editData.email)) {
      errors.email = 'Formato de email inválido';
    }

    setEditErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSave = async () => {
    if (!validateEditForm()) return;

    setIsSaving(true);
    try {
      // Upload new photo first if there is one
      let photoUrl = newPhotoUrl;
      if (photoFile && !newPhotoUrl) {
        photoUrl = await uploadPhoto();
        if (photoUrl) {
          setNewPhotoUrl(photoUrl);
        }
      }

      // NOTA: RFC colaborador y NSS NO se envían al backend (no son editables por seguridad)
      const payload = {
        row_id: profileData.row_id,
        rfc: profileData.rfc,
        nss_original: nss.trim(), // original NSS used for verification
        nombre: editData.nombre || null,
        rfc_empresa: editData.rfc_empresa ? editData.rfc_empresa.toUpperCase() : null,
        email: editData.email || null,
        proveedor: editData.proveedor || null,
        tipo_servicio: editData.tipo_servicio || null,
        url_imagen: photoUrl || null,
      };

      const response = await fetch(`${API_BASE_URL}/v1/onboarding/profile/update`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (response.status === 401) {
        toastService.error('Error de verificación. Vuelve a intentar desde el inicio.');
        setCurrentStep(1);
        return;
      }

      if (!response.ok) {
        throw new Error('Error del servidor');
      }

      const data = await response.json();

      if (data.success) {
        toastService.success('Perfil actualizado exitosamente');
        // Notify about certificate email resend
        if (data.email_sent && data.email_masked) {
          toastService.success(`Certificado actualizado enviado a ${data.email_masked}`);
        } else if (data.email_sent === false) {
          toastService.warning('No se pudo reenviar el certificado por correo. Intenta desde la sección de reenvío.');
        }
        // Update the displayed profile data with the new values
        // NOTA: RFC colaborador y NSS NO se actualizan (no son editables)
        setProfileData(prev => ({
          ...prev,
          nombre: editData.nombre || prev.nombre,
          rfc_empresa: editData.rfc_empresa || prev.rfc_empresa,
          email: editData.email || prev.email,
          proveedor: editData.proveedor || prev.proveedor,
          tipo_servicio: editData.tipo_servicio || prev.tipo_servicio,
          url_imagen: photoUrl || prev.url_imagen,
        }));
        // Clear the new photo state since it's now saved
        setPhotoFile(null);
        setPhotoPreview(null);
      } else {
        toastService.error(data.message || 'Error al guardar los cambios');
      }
    } catch (error) {
      console.error('Error guardando perfil:', error);
      toastService.error('Error al guardar los cambios. Intenta de nuevo.');
    } finally {
      setIsSaving(false);
    }
  };

  // ========== RENDER ==========

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm py-6">
        <div className="max-w-2xl mx-auto px-4 flex justify-center">
          <img src="/images/coca-cola-femsa-logo.png" alt="Coca-Cola FEMSA" className="h-20 md:h-24" />
        </div>
      </header>

      <canvas ref={canvasRef} className="hidden" />

      <main className="max-w-2xl mx-auto px-4 py-12">
        {currentStep === 1 && (
          <div className="bg-white rounded-lg shadow-lg p-8">
            <h1 className="text-2xl font-bold text-gray-800 text-center mb-2">
              Actualizar Mi Perfil
            </h1>
            <p className="text-gray-500 text-center mb-8">
              Ingresa tu RFC y NSS para verificar tu identidad
            </p>

            {verifyErrors.general && (
              <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-sm text-red-600 text-center">{verifyErrors.general}</p>
              </div>
            )}

            <div className="space-y-5">
              {/* RFC */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">RFC del Colaborador</label>
                <input
                  type="text"
                  value={rfc}
                  onChange={e => {
                    setRfc(e.target.value.toUpperCase());
                    if (verifyErrors.rfc) setVerifyErrors(prev => ({ ...prev, rfc: null }));
                  }}
                  placeholder="Ej: PEGJ850101XXX"
                  maxLength={13}
                  className={`w-full px-4 py-3 border rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D91E18] transition ${
                    verifyErrors.rfc ? 'border-red-500' : 'border-gray-300'
                  }`}
                />
                {verifyErrors.rfc && <p className="text-sm text-red-500 mt-1">{verifyErrors.rfc}</p>}
              </div>

              {/* NSS */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">NSS (Número de Seguridad Social)</label>
                <input
                  type="text"
                  value={nss}
                  onChange={e => {
                    const val = e.target.value.replace(/\D/g, '');
                    setNss(val);
                    if (verifyErrors.nss) setVerifyErrors(prev => ({ ...prev, nss: null }));
                  }}
                  placeholder="11 dígitos"
                  maxLength={11}
                  inputMode="numeric"
                  className={`w-full px-4 py-3 border rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D91E18] transition ${
                    verifyErrors.nss ? 'border-red-500' : 'border-gray-300'
                  }`}
                />
                {verifyErrors.nss && <p className="text-sm text-red-500 mt-1">{verifyErrors.nss}</p>}
              </div>

              {/* Verify button */}
              <button
                onClick={handleVerify}
                disabled={isVerifying}
                className="w-full py-3 bg-[#D91E18] text-white font-semibold rounded-lg hover:bg-[#b81915] transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isVerifying ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Verificando...
                  </span>
                ) : 'Verificar'}
              </button>
            </div>
          </div>
        )}

        {currentStep === 2 && profileData && (
          <div className="space-y-6">
            {/* Back button */}
            <button
              onClick={() => { setCurrentStep(1); setProfileData(null); removeNewPhoto(); stopCamera(); }}
              className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              Volver
            </button>

            <div className="bg-white rounded-lg shadow-lg p-8">
              <h1 className="text-2xl font-bold text-gray-800 text-center mb-6">
                Actualizar Mi Perfil
              </h1>

              {/* Photo section */}
              <div className="flex flex-col items-center mb-8">
                <div className="w-40 h-40 rounded-full overflow-hidden bg-gray-200 border-4 border-gray-300 mb-4">
                  {photoPreview ? (
                    <img src={photoPreview} alt="Nueva foto" className="w-full h-full object-cover" />
                  ) : profileData.url_imagen ? (
                    <img src={profileData.url_imagen} alt="Foto actual" className="w-full h-full object-cover" />
                  ) : (
                    <div className="w-full h-full flex flex-col items-center justify-center text-gray-400">
                      <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                      </svg>
                      <span className="text-xs mt-1">SIN FOTO</span>
                    </div>
                  )}
                </div>

                {/* Camera controls */}
                {!isCameraActive && !photoPreview && (
                  <button
                    onClick={startCamera}
                    className="px-4 py-2 bg-gray-700 text-white text-sm font-medium rounded-lg hover:bg-gray-800 transition flex items-center gap-2"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                    Tomar nueva foto
                  </button>
                )}

                {photoPreview && (
                  <button
                    onClick={removeNewPhoto}
                    className="px-4 py-2 text-sm text-red-600 hover:text-red-800 font-medium transition"
                  >
                    Eliminar nueva foto
                  </button>
                )}

                {cameraError && (
                  <p className="text-sm text-red-500 mt-2 text-center max-w-sm">{cameraError}</p>
                )}

                {/* Camera viewfinder */}
                {isCameraActive && (
                  <div className="mt-4 w-full max-w-sm">
                    <div className="relative rounded-lg overflow-hidden bg-black">
                      <video
                        ref={videoRef}
                        autoPlay
                        playsInline
                        muted
                        className="w-full"
                        style={{ transform: 'scaleX(-1)' }}
                      />
                    </div>
                    <div className="flex gap-3 mt-3">
                      <button
                        onClick={capturePhoto}
                        className="flex-1 py-2 bg-[#D91E18] text-white text-sm font-semibold rounded-lg hover:bg-[#b81915] transition"
                      >
                        Capturar
                      </button>
                      <button
                        onClick={stopCamera}
                        className="flex-1 py-2 bg-gray-300 text-gray-700 text-sm font-semibold rounded-lg hover:bg-gray-400 transition"
                      >
                        Cancelar
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Editable fields */}
              <div className="space-y-4 mb-8">
                <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Datos del colaborador</h2>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Nombre</label>
                  <input
                    type="text"
                    value={editData.nombre}
                    onChange={e => handleEditChange('nombre', e.target.value)}
                    placeholder="Nombre completo"
                    className={`w-full px-4 py-3 border rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D91E18] transition ${
                      editErrors.nombre ? 'border-red-500' : 'border-gray-300'
                    }`}
                  />
                  {editErrors.nombre && <p className="text-sm text-red-500 mt-1">{editErrors.nombre}</p>}
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    RFC del Colaborador
                    <span className="text-xs text-gray-500 ml-2">(No editable por seguridad)</span>
                  </label>
                  <input
                    type="text"
                    value={editData.rfc_colaborador}
                    disabled
                    className="w-full px-4 py-3 border border-gray-200 rounded-lg bg-gray-100 text-gray-600 cursor-not-allowed"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">RFC de la Empresa</label>
                  <input
                    type="text"
                    value={editData.rfc_empresa}
                    onChange={e => handleEditChange('rfc_empresa', e.target.value.toUpperCase())}
                    placeholder="Ej: EMP850101XXX"
                    maxLength={13}
                    className={`w-full px-4 py-3 border rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D91E18] transition ${
                      editErrors.rfc_empresa ? 'border-red-500' : 'border-gray-300'
                    }`}
                  />
                  {editErrors.rfc_empresa && <p className="text-sm text-red-500 mt-1">{editErrors.rfc_empresa}</p>}
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Correo Electrónico</label>
                  <input
                    type="email"
                    value={editData.email}
                    onChange={e => handleEditChange('email', e.target.value)}
                    placeholder="correo@ejemplo.com"
                    className={`w-full px-4 py-3 border rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D91E18] transition ${
                      editErrors.email ? 'border-red-500' : 'border-gray-300'
                    }`}
                  />
                  {editErrors.email && <p className="text-sm text-red-500 mt-1">{editErrors.email}</p>}
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    NSS
                    <span className="text-xs text-gray-500 ml-2">(No editable por seguridad)</span>
                  </label>
                  <input
                    type="text"
                    value={editData.nss}
                    disabled
                    className="w-full px-4 py-3 border border-gray-200 rounded-lg bg-gray-100 text-gray-600 cursor-not-allowed"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Proveedor / Empresa</label>
                  <input
                    type="text"
                    value={editData.proveedor}
                    onChange={e => handleEditChange('proveedor', e.target.value)}
                    placeholder="Nombre de la empresa"
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D91E18] transition"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Tipo de Servicio</label>
                  <input
                    type="text"
                    value={editData.tipo_servicio}
                    onChange={e => handleEditChange('tipo_servicio', e.target.value)}
                    placeholder="Ej: Mantenimiento, Limpieza..."
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D91E18] transition"
                  />
                </div>
              </div>

              {/* Save button */}
              <button
                onClick={handleSave}
                disabled={isSaving || isUploadingPhoto}
                className="w-full py-3 bg-[#D91E18] text-white font-semibold rounded-lg hover:bg-[#b81915] transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isSaving || isUploadingPhoto ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    {isUploadingPhoto ? 'Subiendo foto...' : 'Guardando...'}
                  </span>
                ) : 'Guardar cambios'}
              </button>
            </div>
          </div>
        )}
      </main>

      <footer className="bg-gray-100 py-6">
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
            <a href="https://www.entersys.mx/configuracion-de-cookies" className="text-gray-500 hover:text-[#FFC600] transition-colors">Configuración de cookies</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
