/**
 * FormularioCursoSeguridad.jsx
 * Formulario de examen de seguridad dinámico.
 * Las preguntas y categorías se cargan desde la API (base de datos).
 *
 * Criterios de aprobación:
 * - Cada sección debe tener el mínimo configurado en BD (por defecto 80%)
 * - Máximo 3 intentos por RFC
 */

import React, { useState, useMemo, useRef, useCallback, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import { BiLogoFacebookCircle, BiLogoInstagram, BiLogoLinkedinSquare, BiLogoYoutube } from 'react-icons/bi';
import { config } from '../config/environment';

const API_BASE_URL = config.urls.api;

// Color map para categorías (fallback si el backend no envía un color conocido)
const COLOR_MAP = {
  red:   { bg: 'bg-red-500',   light: 'bg-red-50',   border: 'border-red-200',   text: 'text-red-700' },
  blue:  { bg: 'bg-blue-500',  light: 'bg-blue-50',  border: 'border-blue-200',  text: 'text-blue-700' },
  green: { bg: 'bg-green-500', light: 'bg-green-50',  border: 'border-green-200', text: 'text-green-700' },
  gray:  { bg: 'bg-gray-500',  light: 'bg-gray-50',  border: 'border-gray-200',  text: 'text-gray-700' },
};

// Entidades federativas para búsqueda de CURP en RENAPO
const ENTIDADES_FEDERATIVAS = [
  { code: 'AS', name: 'Aguascalientes' },
  { code: 'BC', name: 'Baja California' },
  { code: 'BS', name: 'Baja California Sur' },
  { code: 'CC', name: 'Campeche' },
  { code: 'CL', name: 'Coahuila' },
  { code: 'CM', name: 'Colima' },
  { code: 'CS', name: 'Chiapas' },
  { code: 'CH', name: 'Chihuahua' },
  { code: 'DF', name: 'Ciudad de México' },
  { code: 'DG', name: 'Durango' },
  { code: 'GT', name: 'Guanajuato' },
  { code: 'GR', name: 'Guerrero' },
  { code: 'HG', name: 'Hidalgo' },
  { code: 'JC', name: 'Jalisco' },
  { code: 'MC', name: 'Estado de México' },
  { code: 'MN', name: 'Michoacán' },
  { code: 'MS', name: 'Morelos' },
  { code: 'NT', name: 'Nayarit' },
  { code: 'NL', name: 'Nuevo León' },
  { code: 'OC', name: 'Oaxaca' },
  { code: 'PL', name: 'Puebla' },
  { code: 'QT', name: 'Querétaro' },
  { code: 'QR', name: 'Quintana Roo' },
  { code: 'SP', name: 'San Luis Potosí' },
  { code: 'SL', name: 'Sinaloa' },
  { code: 'SR', name: 'Sonora' },
  { code: 'TC', name: 'Tabasco' },
  { code: 'TS', name: 'Tamaulipas' },
  { code: 'TL', name: 'Tlaxcala' },
  { code: 'VZ', name: 'Veracruz' },
  { code: 'YN', name: 'Yucatán' },
  { code: 'ZS', name: 'Zacatecas' },
  { code: 'NE', name: 'Nacido en el Extranjero' },
];

// Las preguntas y categorías se cargan dinámicamente desde GET /exam-questions

export default function FormularioCursoSeguridad() {
  const navigate = useNavigate();

  // Estado del formulario
  const [formData, setFormData] = useState({
    nombres: '',
    primer_apellido: '',
    segundo_apellido: '',
    rfc_colaborador: '',
    fecha_nacimiento: '',
    sexo: '',
    estado_nacimiento: '',
    rfc_empresa: '',
    nss: '',
    tipo_servicio: '',
    proveedor: '',
    email: '',
    email_confirm: ''
  });

  // Estado para foto de credencial (captura con cámara)
  const [photoFile, setPhotoFile] = useState(null);
  const [photoPreview, setPhotoPreview] = useState(null);
  const [isUploadingPhoto, setIsUploadingPhoto] = useState(false);
  const [isCameraActive, setIsCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState(null);
  const [showPermissionHelp, setShowPermissionHelp] = useState(false);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);

  const [answers, setAnswers] = useState({});
  const [currentStep, setCurrentStep] = useState(1); // 1: datos, 2: examen, 3: resultado
  const [currentSection, setCurrentSection] = useState(1); // Sección actual del examen (1, 2 o 3)
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isCheckingStatus, setIsCheckingStatus] = useState(false);
  const [result, setResult] = useState(null);
  const [errors, setErrors] = useState({});
  const [examStatus, setExamStatus] = useState(null);
  const [statusError, setStatusError] = useState(null);
  const [isBlocked, setIsBlocked] = useState(false); // Nuevo estado para bloqueo
  const [isDownloadingPDF, setIsDownloadingPDF] = useState(false);

  // Estado para auto-generación de RFC
  const [isGeneratingRfc, setIsGeneratingRfc] = useState(false);
  const [rfcBase, setRfcBase] = useState(''); // primeros 10 chars generados
  const [rfcHomoclave, setRfcHomoclave] = useState(''); // últimos 3 chars (editable si no existe en BD)
  const [rfcLocked, setRfcLocked] = useState(false); // true = RFC completo encontrado en BD, no editable
  const [rfcGenerated, setRfcGenerated] = useState(false); // true = ya se generó el RFC
  const [curpData, setCurpData] = useState(null); // datos CURP del servicio
  const [rfcError, setRfcError] = useState(null); // error message

  // Modal de confirmación de datos antes de continuar
  const [showConfirmModal, setShowConfirmModal] = useState(false);

  // Estado dinámico: preguntas y categorías cargadas desde API
  const [examConfig, setExamConfig] = useState(null); // { categories, questions }
  const [isLoadingQuestions, setIsLoadingQuestions] = useState(false);

  // Fetch de preguntas desde el backend
  const fetchExamQuestions = async () => {
    setIsLoadingQuestions(true);
    try {
      const response = await fetch(`${API_BASE_URL}/v1/onboarding/exam-questions`);
      if (!response.ok) throw new Error('Error al cargar las preguntas del examen');
      const data = await response.json();
      setExamConfig(data);
      return data;
    } catch (error) {
      console.error('Error cargando preguntas:', error);
      alert('Error al cargar las preguntas del examen. Por favor recarga la página.');
      return null;
    } finally {
      setIsLoadingQuestions(false);
    }
  };

  // Categorías derivadas de examConfig (ordenadas por display_order)
  const examCategories = useMemo(() => {
    if (!examConfig) return [];
    return [...examConfig.categories].sort((a, b) => a.display_order - b.display_order);
  }, [examConfig]);

  // Preguntas ya vienen aleatorias y con opciones mezcladas desde el backend
  const examQuestions = examConfig?.questions || [];

  // Obtener preguntas de una categoría específica
  const getQuestionsForCategory = (categoryId) => {
    return examQuestions.filter(q => q.category_id === categoryId);
  };

  // Total de preguntas esperadas
  const totalExpectedQuestions = useMemo(() => {
    return examCategories.reduce((sum, cat) => sum + cat.questions_to_show, 0);
  }, [examCategories]);

  // Contar respuestas por categoría
  const getAnsweredCountForCategory = (categoryId) => {
    const catQuestions = getQuestionsForCategory(categoryId);
    return catQuestions.filter(q => answers[q.id]).length;
  };

  // Regex para validación de RFC mexicano (persona física 13 chars, moral 12 chars)
  const RFC_REGEX = /^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$/i;

  // Validar datos personales
  const validatePersonalData = () => {
    const newErrors = {};

    // Nombre(s): requerido + solo letras, espacios y acentos
    if (!formData.nombres.trim()) {
      newErrors.nombres = 'El nombre es obligatorio';
    } else if (!/^[\p{L}\s]+$/u.test(formData.nombres.trim())) {
      newErrors.nombres = 'El nombre solo debe contener letras y espacios';
    }

    // Primer apellido: requerido
    if (!formData.primer_apellido.trim()) {
      newErrors.primer_apellido = 'El primer apellido es obligatorio';
    } else if (!/^[\p{L}\s]+$/u.test(formData.primer_apellido.trim())) {
      newErrors.primer_apellido = 'Solo debe contener letras y espacios';
    }

    // Segundo apellido: opcional pero si se llena, solo letras
    if (formData.segundo_apellido.trim() && !/^[\p{L}\s]+$/u.test(formData.segundo_apellido.trim())) {
      newErrors.segundo_apellido = 'Solo debe contener letras y espacios';
    }

    // RFC Colaborador: auto-generado, validar que esté completo
    if (!rfcGenerated) {
      newErrors.rfc_colaborador = 'Completa los datos personales para generar el RFC';
    } else {
      const rfcVal = (rfcBase + rfcHomoclave).toUpperCase();
      if (rfcVal.length !== 12 && rfcVal.length !== 13) {
        newErrors.rfc_colaborador = 'El RFC debe tener 12 o 13 caracteres';
      } else if (!RFC_REGEX.test(rfcVal)) {
        newErrors.rfc_colaborador = 'Formato de RFC inválido (ej: PEGJ850101XXX)';
      }
    }

    // Fecha de nacimiento: requerida
    if (!formData.fecha_nacimiento) {
      newErrors.fecha_nacimiento = 'La fecha de nacimiento es obligatoria';
    }

    // Sexo: requerido
    if (!formData.sexo) {
      newErrors.sexo = 'El sexo es obligatorio';
    }

    // Estado de nacimiento: requerido
    if (!formData.estado_nacimiento) {
      newErrors.estado_nacimiento = 'El estado de nacimiento es obligatorio';
    }

    // RFC Empresa: requerido + validar formato
    if (!formData.rfc_empresa.trim()) {
      newErrors.rfc_empresa = 'El RFC de la empresa es obligatorio';
    } else {
      const rfcEmpVal = formData.rfc_empresa.trim().toUpperCase();
      if (rfcEmpVal.length !== 12 && rfcEmpVal.length !== 13) {
        newErrors.rfc_empresa = 'El RFC debe tener 12 o 13 caracteres';
      } else if (!RFC_REGEX.test(rfcEmpVal)) {
        newErrors.rfc_empresa = 'Formato de RFC inválido';
      }
    }

    // NSS: requerido + exactamente 11 dígitos
    if (!formData.nss.trim()) {
      newErrors.nss = 'El NSS es obligatorio';
    } else if (!/^\d{11}$/.test(formData.nss.trim())) {
      newErrors.nss = 'El NSS debe ser exactamente 11 dígitos numéricos';
    }

    // Tipo de servicio: requerido
    if (!formData.tipo_servicio.trim()) {
      newErrors.tipo_servicio = 'El tipo de servicio es obligatorio';
    }

    // Proveedor: requerido
    if (!formData.proveedor.trim()) {
      newErrors.proveedor = 'El proveedor es obligatorio';
    }

    // Email: requerido + validación estricta
    if (!formData.email.trim()) {
      newErrors.email = 'El email es obligatorio';
    } else if (!/^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$/.test(formData.email.trim())) {
      newErrors.email = 'Ingresa un email válido';
    }

    // Email confirmación: debe coincidir con email
    if (!formData.email_confirm.trim()) {
      newErrors.email_confirm = 'Confirma tu correo electrónico';
    } else if (formData.email.trim().toLowerCase() !== formData.email_confirm.trim().toLowerCase()) {
      newErrors.email_confirm = 'Los correos electrónicos no coinciden';
    }

    // Foto de credencial: requerida
    if (!photoFile) {
      newErrors.photo = 'La foto de credencial es obligatoria';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  // Manejar cambio en inputs
  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
    if (errors[name]) {
      setErrors(prev => ({ ...prev, [name]: null }));
    }
    // Resetear RFC generado si cambian campos que afectan la generación
    const rfcTriggerFields = ['nombres', 'primer_apellido', 'segundo_apellido', 'fecha_nacimiento', 'sexo', 'estado_nacimiento', 'email', 'nss'];
    if (rfcTriggerFields.includes(name) && rfcGenerated) {
      setRfcGenerated(false);
      setRfcBase('');
      setRfcHomoclave('');
      setRfcLocked(false);
      setCurpData(null);
      setRfcError(null);
      setFormData(prev => ({ ...prev, [name]: value, rfc_colaborador: '' }));
      return; // already set formData above
    }
  };

  // Manejar cambio en homoclave (3 últimos chars del RFC)
  const handleHomoclaveChange = (e) => {
    const val = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '').substring(0, 3);
    setRfcHomoclave(val);
    setFormData(prev => ({ ...prev, rfc_colaborador: rfcBase + val }));
    if (errors.rfc_colaborador) setErrors(prev => ({ ...prev, rfc_colaborador: null }));
  };

  // Detectar navegador y dispositivo
  const getBrowserName = useCallback(() => {
    const userAgent = navigator.userAgent.toLowerCase();
    if (userAgent.includes('edg')) return 'edge';
    if (userAgent.includes('chrome')) return 'chrome';
    if (userAgent.includes('firefox')) return 'firefox';
    if (userAgent.includes('safari')) return 'safari';
    return 'otro';
  }, []);

  const isMobile = useCallback(() => {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
  }, []);

  const isIOS = useCallback(() => {
    return /iPhone|iPad|iPod/i.test(navigator.userAgent);
  }, []);

  // Iniciar cámara (idéntico a producción)
  const startCamera = useCallback(async () => {
    setCameraError(null);
    setShowPermissionHelp(false);

    try {
      // Paso 1: Verificar estado del permiso
      let permState = 'unknown';
      try {
        if (navigator.permissions && navigator.permissions.query) {
          permState = (await navigator.permissions.query({ name: 'camera' })).state;
        }
      } catch (e) {
        permState = 'query-not-supported';
      }

      // Si el permiso está bloqueado, mostrar instrucciones sin intentar getUserMedia
      if (permState === 'denied') {
        setCameraError(
          'El permiso de cámara está bloqueado. Debes habilitarlo manualmente en la configuración del navegador.'
        );
        setShowPermissionHelp(true);
        return;
      }

      // Paso 2: Solicitar acceso a la cámara (el navegador muestra diálogo nativo si permState es "prompt")
      const constraints = {
        video: {
          facingMode: 'user',
          width: { ideal: isMobile() ? 480 : 640 },
          height: { ideal: isMobile() ? 640 : 800 }
        },
        audio: false
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
      // Fallback con constraints simples
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
        } catch (e) {
          // continuar al manejo de errores
        }
      }

      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        setShowPermissionHelp(true);
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        setCameraError('No se encontró ninguna cámara en tu dispositivo.');
      } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
        setCameraError('La cámara está ocupada. Cierra otras apps que la usen e intenta de nuevo.');
      } else if (err.name === 'AbortError') {
        setCameraError('Se canceló el acceso a la cámara. Intenta de nuevo.');
      } else if (err.name === 'SecurityError') {
        setCameraError('Error de seguridad. Asegúrate de usar HTTPS.');
      } else if (err.name === 'TypeError') {
        setCameraError('Tu navegador no soporta acceso a la cámara.');
      } else {
        setCameraError(`Error: ${err.name || 'Desconocido'} - ${err.message || 'Intenta recargar la página'}`);
      }
    }
  }, [isMobile]);

  // Detener cámara
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

  // Capturar foto desde el video
  const capturePhoto = useCallback(() => {
    if (!videoRef.current || !canvasRef.current) return;

    const video = videoRef.current;
    const canvas = canvasRef.current;

    // Configurar canvas con las dimensiones del video
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const ctx = canvas.getContext('2d');
    // Voltear horizontalmente para efecto espejo
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(video, 0, 0);

    // Convertir canvas a blob
    canvas.toBlob((blob) => {
      if (blob) {
        // Crear archivo desde blob
        const file = new File([blob], `foto_${Date.now()}.jpg`, { type: 'image/jpeg' });
        setPhotoFile(file);
        setPhotoPreview(canvas.toDataURL('image/jpeg', 0.9));
        setErrors(prev => ({ ...prev, photo: null }));
        stopCamera();
      }
    }, 'image/jpeg', 0.9);
  }, [stopCamera]);

  // Eliminar foto y permitir tomar otra
  const handleRemovePhoto = useCallback(() => {
    setPhotoFile(null);
    setPhotoPreview(null);
  }, []);

  // Limpiar cámara al desmontar componente
  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }
    };
  }, []);

  // Subir foto a GCS
  const uploadPhoto = async () => {
    if (!photoFile || !formData.rfc_colaborador) return null;

    setIsUploadingPhoto(true);
    try {
      const formDataUpload = new FormData();
      formDataUpload.append('file', photoFile);
      formDataUpload.append('rfc', formData.rfc_colaborador.toUpperCase());

      const response = await fetch(`${API_BASE_URL}/v1/onboarding/upload-photo`, {
        method: 'POST',
        body: formDataUpload
      });

      if (!response.ok) {
        throw new Error('Error al subir la foto');
      }

      const data = await response.json();
      return data.url;
    } catch (error) {
      console.error('Error subiendo foto:', error);
      setErrors(prev => ({ ...prev, photo: 'Error al subir la foto. Intenta de nuevo.' }));
      return null;
    } finally {
      setIsUploadingPhoto(false);
    }
  };

  // Manejar selección de respuesta
  const handleAnswerSelect = (questionId, answer) => {
    setAnswers(prev => ({ ...prev, [questionId]: answer }));
  };

  // Verificar estatus del examen por RFC
  const checkExamStatus = async () => {
    if (!formData.rfc_colaborador || formData.rfc_colaborador.length < 10) {
      setErrors(prev => ({ ...prev, rfc_colaborador: 'El RFC debe tener al menos 10 caracteres' }));
      return null;
    }

    setIsCheckingStatus(true);
    setStatusError(null);

    try {
      const response = await fetch(
        `${API_BASE_URL}/v1/onboarding/check-exam-status/${formData.rfc_colaborador.toUpperCase()}`
      );
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Error al verificar estatus');
      }

      setExamStatus(data);
      return data;
    } catch (error) {
      console.error('Error verificando estatus:', error);
      setStatusError(error.message);
      return null;
    } finally {
      setIsCheckingStatus(false);
    }
  };

  // Generar RFC base (10 chars) desde RENAPO y buscar en Smartsheet
  const generateAndLookupRfc = async () => {
    setIsGeneratingRfc(true);
    setRfcError(null);
    setCurpData(null);
    setRfcGenerated(false);
    setRfcBase('');
    setRfcHomoclave('');
    setRfcLocked(false);

    try {
      // Paso 1: Obtener CURP/RFC base desde RENAPO
      const [year, month, day] = formData.fecha_nacimiento.split('-');
      const fechaRenapo = `${day}/${month}/${year}`;

      const payload = {
        nombres: formData.nombres.trim().toUpperCase(),
        primer_apellido: formData.primer_apellido.trim().toUpperCase(),
        segundo_apellido: formData.segundo_apellido.trim().toUpperCase(),
        fecha_nacimiento: fechaRenapo,
        sexo: formData.sexo,
        clave_entidad: formData.estado_nacimiento,
      };

      const curpResponse = await fetch(`${API_BASE_URL}/v1/curp/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const curpResult = await curpResponse.json();

      if (!curpResponse.ok) {
        const detail = curpResult.detail || curpResult;
        const message = typeof detail === 'object' ? (detail.message || 'Error al generar RFC') : String(detail);
        setRfcError(message);
        return;
      }

      if (!curpResult.success || !curpResult.data || curpResult.data.length === 0) {
        setRfcError('No se encontraron registros con los datos proporcionados. Verifica que tu información sea correcta.');
        return;
      }

      const matchingRecord = curpResult.data[0];
      const generatedBase = matchingRecord.curp ? matchingRecord.curp.substring(0, 10) : '';

      if (!generatedBase || generatedBase.length < 10) {
        setRfcError('No se pudo generar el RFC base. Verifica tus datos personales.');
        return;
      }

      setCurpData(matchingRecord);

      // Paso 2: Buscar en Smartsheet por NSS + email
      try {
        const lookupResponse = await fetch(
          `${API_BASE_URL}/v1/onboarding/lookup-rfc?nss=${encodeURIComponent(formData.nss.trim())}&email=${encodeURIComponent(formData.email.trim())}`
        );
        const lookupData = await lookupResponse.json();

        if (lookupResponse.ok && lookupData && lookupData.rfc) {
          // RFC encontrado en Smartsheet
          const foundRfc = lookupData.rfc.toUpperCase();
          const foundBase = foundRfc.substring(0, 10);
          const foundHomoclave = foundRfc.substring(10);
          setRfcBase(foundBase);
          setRfcHomoclave(foundHomoclave);
          setRfcLocked(true);
          setFormData(prev => ({ ...prev, rfc_colaborador: foundRfc }));
        } else {
          // No encontrado en Smartsheet, usuario debe ingresar homoclave
          setRfcBase(generatedBase);
          setRfcHomoclave('');
          setRfcLocked(false);
          setFormData(prev => ({ ...prev, rfc_colaborador: generatedBase }));
        }
      } catch (lookupErr) {
        // Si falla el lookup, continuar solo con base generada
        console.warn('Error en lookup de RFC:', lookupErr);
        setRfcBase(generatedBase);
        setRfcHomoclave('');
        setRfcLocked(false);
        setFormData(prev => ({ ...prev, rfc_colaborador: generatedBase }));
      }

      setRfcGenerated(true);

    } catch (error) {
      console.error('Error generando RFC:', error);
      setRfcError('Error de conexión al generar RFC. Intenta nuevamente.');
    } finally {
      setIsGeneratingRfc(false);
    }
  };

  // Auto-trigger: generar RFC cuando todos los campos necesarios están llenos
  useEffect(() => {
    const { nombres, primer_apellido, fecha_nacimiento, sexo, estado_nacimiento, email, nss } = formData;
    const allFilled = nombres.trim() && primer_apellido.trim() && fecha_nacimiento && sexo && estado_nacimiento && email.trim() && nss.trim();

    if (!allFilled) return;
    if (rfcGenerated || isGeneratingRfc) return;

    const timer = setTimeout(() => {
      generateAndLookupRfc();
    }, 800);

    return () => clearTimeout(timer);
  }, [formData.nombres, formData.primer_apellido, formData.fecha_nacimiento, formData.sexo, formData.estado_nacimiento, formData.email, formData.nss]); // eslint-disable-line react-hooks/exhaustive-deps

  // Continuar al examen: valida datos, luego muestra modal de confirmación
  const handleContinueToExam = async () => {
    if (!validatePersonalData()) return;

    // Mostrar modal de confirmación de datos
    setShowConfirmModal(true);
  };

  // Confirmar datos y proceder al examen (se ejecuta desde el modal)
  const handleConfirmAndProceed = async () => {
    setShowConfirmModal(false);

    const status = await checkExamStatus();

    if (!status) {
      const config = await fetchExamQuestions();
      if (!config) return;
      setCurrentStep(2);
      setCurrentSection(1);
      window.scrollTo(0, 0);
      return;
    }

    if (!status.can_take_exam) {
      setStatusError(status.message);
      setIsBlocked(true);
      return;
    }

    const examData = await fetchExamQuestions();
    if (!examData) return;
    setCurrentStep(2);
    setCurrentSection(1);
    window.scrollTo(0, 0);
  };

  // Navegar entre secciones del examen
  const goToSection = (sectionId) => {
    setCurrentSection(sectionId);
    window.scrollTo(0, 0);
  };

  // Enviar examen
  const handleSubmit = async () => {
    // Verificar que todas las preguntas estén contestadas
    const totalAnswered = Object.keys(answers).length;
    if (totalAnswered < totalExpectedQuestions) {
      alert(`Por favor responde todas las preguntas antes de enviar. Faltan ${totalExpectedQuestions - totalAnswered} preguntas.`);
      return;
    }

    setIsSubmitting(true);

    try {
      // Subir foto (obligatoria)
      let photoUrl = null;
      if (photoFile) {
        photoUrl = await uploadPhoto();
        if (!photoUrl) {
          alert('Error al subir la foto de credencial. Por favor intenta de nuevo.');
          setIsSubmitting(false);
          return;
        }
      } else {
        alert('La foto de credencial es obligatoria.');
        setIsSubmitting(false);
        return;
      }

      // Preparar respuestas SIN is_correct (el backend valida contra BD)
      const formattedAnswers = examQuestions.map(q => ({
        question_id: q.id,
        answer: answers[q.id] || '',
      }));

      // Construir nombre_completo a partir de los campos separados
      const nombreCompleto = [formData.nombres, formData.primer_apellido, formData.segundo_apellido]
        .map(s => s.trim())
        .filter(Boolean)
        .join(' ');

      // Excluir campos internos del payload enviado al backend
      const { email_confirm, nombres, primer_apellido, segundo_apellido, fecha_nacimiento, sexo, estado_nacimiento, ...formDataBase } = formData;
      const payload = {
        ...formDataBase,
        nombre_completo: nombreCompleto,
        url_imagen: photoUrl,
        answers: formattedAnswers
      };

      const response = await fetch(`${API_BASE_URL}/v1/onboarding/submit-exam`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });

      const data = await response.json();

      setResult(data);
      setCurrentStep(3);
      window.scrollTo(0, 0);

    } catch (error) {
      console.error('Error enviando examen:', error);
      alert('Error al enviar el examen. Por favor intenta de nuevo.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Volver a intentar el examen (carga nuevas preguntas aleatorias del backend)
  const handleRetry = async () => {
    setAnswers({});
    setResult(null);
    const examData = await fetchExamQuestions();
    if (!examData) return;
    setCurrentStep(2);
    setCurrentSection(1);
    window.scrollTo(0, 0);
  };

  // Volver a ver el video
  const handleWatchVideo = () => {
    navigate('/curso-seguridad');
  };

  // Descargar certificado PDF
  const handleDownloadPDF = async () => {
    if (!formData.rfc_colaborador) return;

    setIsDownloadingPDF(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/v1/onboarding/download-certificate/${formData.rfc_colaborador.toUpperCase()}`
      );

      if (!response.ok) {
        throw new Error('Error al generar el PDF');
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `certificado_${formData.rfc_colaborador.toUpperCase()}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Error descargando PDF:', error);
      alert('Error al descargar el certificado PDF. Intenta de nuevo.');
    } finally {
      setIsDownloadingPDF(false);
    }
  };

  // Bloquear copiar/pegar en campo de confirmación de email
  const handleBlockPaste = (e) => {
    e.preventDefault();
  };

  // Renderizar paso 1: Datos personales
  const renderPersonalDataStep = () => (
    <div className="max-w-2xl mx-auto">
      <div className="bg-white rounded-lg shadow-lg p-8">
        <h2 className="text-2xl font-bold text-gray-900 mb-6">Datos del Colaborador</h2>
        <p className="text-gray-600 mb-6">
          Complete la siguiente información antes de iniciar el examen de certificación.
        </p>

        {/* Nota informativa */}
        <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <div className="flex items-start">
            <svg className="w-5 h-5 text-blue-500 mr-3 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div>
              <p className="text-blue-800 font-semibold text-sm">Nota importante</p>
              <p className="text-blue-700 text-sm mt-1">
                Tus datos ser&aacute;n verificados para garantizar la validez de tu certificaci&oacute;n.
                Por favor aseg&uacute;rate de ingresar tu informaci&oacute;n tal como aparece en tus documentos oficiales.
              </p>
            </div>
          </div>
        </div>

        {/* Mensaje especial cuando ya tiene certificación vigente */}
        {examStatus && examStatus.is_approved && !examStatus.is_expired && (
          <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-lg">
            <div className="flex items-start">
              <svg className="w-6 h-6 text-green-600 mr-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <p className="text-green-800 font-semibold">¡Ya tienes una certificación vigente!</p>
                <p className="text-green-700 text-sm mt-1">
                  Tu certificación de seguridad sigue activa y no necesitas volver a realizar el examen.
                </p>
                {examStatus.expiration_date && (
                  <p className="text-green-700 text-sm mt-1">
                    <strong>Vigente hasta:</strong> {examStatus.expiration_date}
                  </p>
                )}
                {examStatus.certificate_resent && (
                  <p className="text-green-600 text-sm mt-2 font-medium">
                    ✉️ Hemos reenviado tu certificado con código QR a tu correo electrónico registrado.
                  </p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Mensaje cuando la certificación expiró pero puede renovar */}
        {examStatus && examStatus.is_approved && examStatus.is_expired && (
          <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-lg">
            <div className="flex items-start">
              <svg className="w-6 h-6 text-amber-600 mr-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <p className="text-amber-800 font-semibold">Tu certificación ha expirado</p>
                <p className="text-amber-700 text-sm mt-1">
                  Tu certificación anterior venció. Puedes realizar el examen nuevamente para renovarla.
                </p>
                {examStatus.expiration_date && (
                  <p className="text-amber-600 text-sm mt-1">
                    <strong>Venció el:</strong> {examStatus.expiration_date}
                  </p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Mensaje de error de estatus (cuando no puede hacer examen) */}
        {statusError && !examStatus?.is_approved && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-red-800 font-medium">{statusError}</p>
            {examStatus && !examStatus.can_take_exam && examStatus.attempts_used >= 3 && (
              <p className="text-red-600 text-sm mt-2">
                Has agotado tus 3 intentos. Contacta al administrador para más información.
              </p>
            )}
          </div>
        )}

        {/* Mostrar estatus si ya hay intentos (pero no aprobado) */}
        {examStatus && examStatus.attempts_used > 0 && examStatus.can_take_exam && !examStatus.is_approved && (
          <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-lg">
            <p className="text-amber-800 font-medium">
              Ya tienes {examStatus.attempts_used} intento(s) registrado(s).
            </p>
            <p className="text-amber-700 text-sm mt-1">
              Te quedan {examStatus.attempts_remaining} intento(s) disponible(s).
            </p>
          </div>
        )}

        <div className="space-y-6">
          {/* 1. Nombre(s) */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Nombre(s) <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              name="nombres"
              value={formData.nombres}
              onChange={handleInputChange}
              className={`w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-[#D91E18] focus:border-transparent ${
                errors.nombres ? 'border-red-500' : 'border-gray-300'
              }`}
              placeholder="Juan Carlos"
            />
            {errors.nombres && (
              <p className="mt-1 text-sm text-red-500">{errors.nombres}</p>
            )}
          </div>

          {/* 2. Primer Apellido */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Primer Apellido <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              name="primer_apellido"
              value={formData.primer_apellido}
              onChange={handleInputChange}
              className={`w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-[#D91E18] focus:border-transparent ${
                errors.primer_apellido ? 'border-red-500' : 'border-gray-300'
              }`}
              placeholder="Pérez"
            />
            {errors.primer_apellido && (
              <p className="mt-1 text-sm text-red-500">{errors.primer_apellido}</p>
            )}
          </div>

          {/* 3. Segundo Apellido */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Segundo Apellido
            </label>
            <input
              type="text"
              name="segundo_apellido"
              value={formData.segundo_apellido}
              onChange={handleInputChange}
              className={`w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-[#D91E18] focus:border-transparent ${
                errors.segundo_apellido ? 'border-red-500' : 'border-gray-300'
              }`}
              placeholder="García"
            />
            {errors.segundo_apellido && (
              <p className="mt-1 text-sm text-red-500">{errors.segundo_apellido}</p>
            )}
          </div>

          {/* 4. Fecha de Nacimiento */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Fecha de Nacimiento <span className="text-red-500">*</span>
            </label>
            <input
              type="date"
              name="fecha_nacimiento"
              value={formData.fecha_nacimiento}
              onChange={handleInputChange}
              max={new Date().toISOString().split('T')[0]}
              min="1930-01-01"
              className={`w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-[#D91E18] focus:border-transparent ${
                errors.fecha_nacimiento ? 'border-red-500' : 'border-gray-300'
              }`}
            />
            {errors.fecha_nacimiento && (
              <p className="mt-1 text-sm text-red-500">{errors.fecha_nacimiento}</p>
            )}
          </div>

          {/* 5. Sexo */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Sexo <span className="text-red-500">*</span>
            </label>
            <select
              name="sexo"
              value={formData.sexo}
              onChange={handleInputChange}
              className={`w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-[#D91E18] focus:border-transparent bg-white ${
                errors.sexo ? 'border-red-500' : 'border-gray-300'
              }`}
            >
              <option value="">Selecciona...</option>
              <option value="H">Hombre</option>
              <option value="M">Mujer</option>
            </select>
            {errors.sexo && (
              <p className="mt-1 text-sm text-red-500">{errors.sexo}</p>
            )}
          </div>

          {/* 6. Estado de Nacimiento */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Estado de Nacimiento <span className="text-red-500">*</span>
            </label>
            <select
              name="estado_nacimiento"
              value={formData.estado_nacimiento}
              onChange={handleInputChange}
              className={`w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-[#D91E18] focus:border-transparent bg-white ${
                errors.estado_nacimiento ? 'border-red-500' : 'border-gray-300'
              }`}
            >
              <option value="">Selecciona tu estado...</option>
              {ENTIDADES_FEDERATIVAS.map(ent => (
                <option key={ent.code} value={ent.code}>{ent.name}</option>
              ))}
            </select>
            {errors.estado_nacimiento && (
              <p className="mt-1 text-sm text-red-500">{errors.estado_nacimiento}</p>
            )}
          </div>

          {/* 7. Correo Electrónico */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Correo Electrónico <span className="text-red-500">*</span>
            </label>
            <input
              type="email"
              name="email"
              value={formData.email}
              onChange={handleInputChange}
              className={`w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-[#D91E18] focus:border-transparent ${
                errors.email ? 'border-red-500' : 'border-gray-300'
              }`}
              placeholder="correo@ejemplo.com"
            />
            {errors.email && (
              <p className="mt-1 text-sm text-red-500">{errors.email}</p>
            )}
          </div>

          {/* 8. Confirmar Correo Electrónico */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Confirmar Correo Electrónico <span className="text-red-500">*</span>
            </label>
            <input
              type="email"
              name="email_confirm"
              value={formData.email_confirm}
              onChange={handleInputChange}
              onPaste={handleBlockPaste}
              onCopy={handleBlockPaste}
              onCut={handleBlockPaste}
              className={`w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-[#D91E18] focus:border-transparent ${
                errors.email_confirm ? 'border-red-500' : 'border-gray-300'
              }`}
              placeholder="Vuelve a escribir tu correo"
            />
            {errors.email_confirm && (
              <p className="mt-1 text-sm text-red-500">{errors.email_confirm}</p>
            )}
            <p className="mt-1 text-xs text-gray-400">Escribe tu correo nuevamente para confirmar. No se permite copiar y pegar.</p>
          </div>

          {/* 9. NSS del Colaborador */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              NSS del Colaborador <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              name="nss"
              value={formData.nss}
              onChange={handleInputChange}
              maxLength={11}
              className={`w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-[#D91E18] focus:border-transparent ${
                errors.nss ? 'border-red-500' : 'border-gray-300'
              }`}
              placeholder="12345678901"
            />
            {errors.nss && (
              <p className="mt-1 text-sm text-red-500">{errors.nss}</p>
            )}
          </div>

          {/* 10. Loader de generación de RFC */}
          {isGeneratingRfc && (
            <div className="flex items-center justify-center py-4">
              <svg className="animate-spin h-6 w-6 text-[#D91E18] mr-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              <span className="text-sm text-gray-600">Generando RFC...</span>
            </div>
          )}

          {/* 11. RFC del Colaborador - SPECIAL INPUT */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              RFC del Colaborador <span className="text-red-500">*</span>
            </label>

            {/* Estado: aún no se ha generado */}
            {!rfcGenerated && !isGeneratingRfc && (
              <input
                type="text"
                disabled
                value=""
                className="w-full px-4 py-3 border border-gray-300 rounded-lg bg-gray-100 text-gray-400 cursor-not-allowed"
                placeholder="Se generará automáticamente"
              />
            )}

            {/* Estado: RFC completo encontrado en BD (locked) */}
            {rfcGenerated && rfcLocked && (
              <input
                type="text"
                disabled
                value={rfcBase + rfcHomoclave}
                className="w-full px-4 py-3 border-2 border-green-500 rounded-lg bg-green-50 text-gray-900 font-mono uppercase cursor-not-allowed"
              />
            )}

            {/* Estado: RFC base generado, homoclave editable */}
            {rfcGenerated && !rfcLocked && (
              <div className="flex items-stretch">
                <input
                  type="text"
                  disabled
                  value={rfcBase}
                  className="flex-shrink-0 w-[10ch] px-3 py-3 border border-gray-300 rounded-l-lg bg-gray-100 text-gray-700 font-mono uppercase cursor-not-allowed text-center"
                  style={{ minWidth: '130px' }}
                />
                <input
                  type="text"
                  value={rfcHomoclave}
                  onChange={handleHomoclaveChange}
                  maxLength={3}
                  className={`w-[5ch] px-3 py-3 border border-l-0 rounded-r-lg focus:ring-2 focus:ring-[#D91E18] focus:border-transparent font-mono uppercase text-center ${
                    errors.rfc_colaborador ? 'border-red-500' : 'border-gray-300'
                  }`}
                  placeholder="XXX"
                  style={{ minWidth: '70px' }}
                />
              </div>
            )}

            {/* Indicadores de estado del RFC */}
            {rfcGenerated && curpData && (
              <p className="mt-2 text-sm text-blue-700">
                <span className="font-medium">CURP:</span> {curpData.curp}
              </p>
            )}
            {rfcError && (
              <p className="mt-2 text-sm text-red-600">{rfcError}</p>
            )}
            {rfcGenerated && rfcLocked && (
              <p className="mt-2 text-sm text-green-700 font-medium">RFC encontrado en registros anteriores</p>
            )}
            {rfcGenerated && !rfcLocked && (
              <p className="mt-2 text-sm text-amber-700">Ingresa los últimos 3 caracteres de tu RFC (homoclave)</p>
            )}

            {errors.rfc_colaborador && (
              <p className="mt-1 text-sm text-red-500">{errors.rfc_colaborador}</p>
            )}
          </div>

          {/* 12. RFC de la Empresa */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              RFC de la Empresa <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              name="rfc_empresa"
              value={formData.rfc_empresa}
              onChange={handleInputChange}
              maxLength={13}
              className={`w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-[#D91E18] focus:border-transparent uppercase ${
                errors.rfc_empresa ? 'border-red-500' : 'border-gray-300'
              }`}
              placeholder="EMP850101XXX"
            />
            {errors.rfc_empresa && (
              <p className="mt-1 text-sm text-red-500">{errors.rfc_empresa}</p>
            )}
          </div>

          {/* 13. Tipo de Servicio */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Tipo de Servicio <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              name="tipo_servicio"
              value={formData.tipo_servicio}
              onChange={handleInputChange}
              className={`w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-[#D91E18] focus:border-transparent ${
                errors.tipo_servicio ? 'border-red-500' : 'border-gray-300'
              }`}
              placeholder="Ej: Mantenimiento, Limpieza, Seguridad, etc."
            />
            {errors.tipo_servicio && (
              <p className="mt-1 text-sm text-red-500">{errors.tipo_servicio}</p>
            )}
          </div>

          {/* 14. Proveedor / Empresa */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Proveedor / Empresa <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              name="proveedor"
              value={formData.proveedor}
              onChange={handleInputChange}
              className={`w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-[#D91E18] focus:border-transparent ${
                errors.proveedor ? 'border-red-500' : 'border-gray-300'
              }`}
              placeholder="Nombre de la empresa proveedora"
            />
            {errors.proveedor && (
              <p className="mt-1 text-sm text-red-500">{errors.proveedor}</p>
            )}
          </div>

          {/* 15. Foto para Credencial */}
          <div className="pt-6 border-t border-gray-200">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Foto para Credencial de Acceso <span className="text-red-500">*</span>
            </label>

            {/* Requisitos de la foto */}
            <div className="mb-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <p className="text-sm font-medium text-blue-800 mb-2">Para tomar tu foto:</p>
              <ul className="text-sm text-blue-700 space-y-1">
                <li className="flex items-center gap-2">
                  <svg className="w-4 h-4 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  Ubícate en un lugar con buena iluminación
                </li>
                <li className="flex items-center gap-2">
                  <svg className="w-4 h-4 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  Centra tu rostro (sin lentes oscuros ni gorra)
                </li>
                <li className="flex items-center gap-2">
                  <svg className="w-4 h-4 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  Busca un fondo liso (preferentemente claro)
                </li>
                <li className="flex items-center gap-2">
                  <svg className="w-4 h-4 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  Permite el acceso a la cámara cuando se solicite
                </li>
              </ul>
            </div>

            {/* Canvas oculto para captura */}
            <canvas ref={canvasRef} className="hidden" />

            {/* Modal de ayuda para permisos de cámara */}
            {showPermissionHelp && (
              <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
                <div className="bg-white rounded-xl shadow-2xl max-w-md w-full max-h-[90vh] overflow-y-auto">
                  <div className="p-6">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="text-lg font-bold text-gray-900">Permitir acceso a la cámara</h3>
                      <button
                        onClick={() => setShowPermissionHelp(false)}
                        className="text-gray-400 hover:text-gray-600"
                      >
                        <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>

                    <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
                      <p className="text-sm text-red-800 font-medium mb-1">
                        El permiso de cámara está BLOQUEADO
                      </p>
                      <p className="text-xs text-red-700">
                        El navegador no puede mostrar el diálogo de permiso porque fue bloqueado anteriormente.
                        Debes habilitarlo manualmente siguiendo los pasos de abajo.
                      </p>
                      {cameraError && (
                        <p className="text-xs text-red-600 mt-2 font-mono bg-red-100 p-1 rounded">
                          {cameraError}
                        </p>
                      )}
                    </div>

                    {/* Instrucciones para Chrome/Edge */}
                    {(getBrowserName() === 'chrome' || getBrowserName() === 'edge') && (
                      <div className="space-y-3">
                        <p className="text-sm font-medium text-gray-700">Sigue estos pasos:</p>
                        <ol className="text-sm text-gray-600 space-y-2 list-decimal list-inside">
                          <li>Haz clic en el icono de candado <span className="inline-flex items-center px-1 py-0.5 bg-gray-100 rounded text-xs">🔒</span> en la barra de direcciones</li>
                          <li>Busca la opción <strong>"Cámara"</strong></li>
                          <li>Cámbiala a <strong>"Permitir"</strong></li>
                          <li>Recarga la página o haz clic en "Reintentar"</li>
                        </ol>
                        <div className="mt-4 p-3 bg-gray-100 rounded-lg">
                          <p className="text-xs text-gray-500 mb-2">O copia esta dirección en tu navegador:</p>
                          <code className="text-xs bg-white px-2 py-1 rounded border block break-all">
                            {getBrowserName() === 'chrome' ? 'chrome://settings/content/camera' : 'edge://settings/content/camera'}
                          </code>
                        </div>
                      </div>
                    )}

                    {/* Instrucciones para Firefox */}
                    {getBrowserName() === 'firefox' && (
                      <div className="space-y-3">
                        <p className="text-sm font-medium text-gray-700">Sigue estos pasos:</p>
                        <ol className="text-sm text-gray-600 space-y-2 list-decimal list-inside">
                          <li>Haz clic en el icono de escudo/candado en la barra de direcciones</li>
                          <li>Haz clic en <strong>"Permisos"</strong></li>
                          <li>Busca <strong>"Usar la cámara"</strong> y haz clic en la X para quitar el bloqueo</li>
                          <li>Recarga la página o haz clic en "Reintentar"</li>
                        </ol>
                      </div>
                    )}

                    {/* Instrucciones para Safari */}
                    {getBrowserName() === 'safari' && (
                      <div className="space-y-3">
                        <p className="text-sm font-medium text-gray-700">Sigue estos pasos:</p>
                        <ol className="text-sm text-gray-600 space-y-2 list-decimal list-inside">
                          <li>Ve a <strong>Safari → Preferencias → Sitios web</strong></li>
                          <li>Selecciona <strong>"Cámara"</strong> en el menú izquierdo</li>
                          <li>Busca este sitio y cámbialo a <strong>"Permitir"</strong></li>
                          <li>Recarga la página</li>
                        </ol>
                      </div>
                    )}

                    {/* Instrucciones genéricas */}
                    {getBrowserName() === 'otro' && !isMobile() && (
                      <div className="space-y-3">
                        <p className="text-sm font-medium text-gray-700">Sigue estos pasos:</p>
                        <ol className="text-sm text-gray-600 space-y-2 list-decimal list-inside">
                          <li>Busca el icono de candado o configuración en la barra de direcciones</li>
                          <li>Busca los permisos del sitio o configuración de cámara</li>
                          <li>Permite el acceso a la cámara para este sitio</li>
                          <li>Recarga la página</li>
                        </ol>
                      </div>
                    )}

                    {/* Instrucciones para iOS (iPhone/iPad) */}
                    {isIOS() && (
                      <div className="space-y-3">
                        <p className="text-sm font-medium text-gray-700">En tu iPhone/iPad:</p>
                        <ol className="text-sm text-gray-600 space-y-2 list-decimal list-inside">
                          <li>Abre <strong>Configuración</strong> (⚙️) de tu dispositivo</li>
                          <li>Busca <strong>Safari</strong> (o el navegador que uses)</li>
                          <li>Toca <strong>Cámara</strong></li>
                          <li>Selecciona <strong>"Permitir"</strong></li>
                          <li>Regresa aquí y toca "Reintentar"</li>
                        </ol>
                        <div className="mt-3 p-3 bg-blue-50 rounded-lg">
                          <p className="text-xs text-blue-700">
                            💡 También puedes tocar el icono <strong>"aA"</strong> en la barra de Safari y seleccionar "Configuración del sitio web"
                          </p>
                        </div>
                      </div>
                    )}

                    {/* Instrucciones para Android */}
                    {isMobile() && !isIOS() && (
                      <div className="space-y-3">
                        <p className="text-sm font-medium text-gray-700">En tu dispositivo Android:</p>
                        <ol className="text-sm text-gray-600 space-y-2 list-decimal list-inside">
                          <li>Toca el icono de <strong>candado 🔒</strong> en la barra de direcciones</li>
                          <li>Toca <strong>"Permisos"</strong></li>
                          <li>Activa el permiso de <strong>"Cámara"</strong></li>
                          <li>Toca "Reintentar" abajo</li>
                        </ol>
                        <div className="mt-3 p-3 bg-blue-50 rounded-lg">
                          <p className="text-xs text-blue-700">
                            💡 Si no aparece, ve a Configuración del teléfono → Apps → Chrome → Permisos → Cámara
                          </p>
                        </div>
                      </div>
                    )}

                    <div className="mt-6 flex gap-3">
                      <button
                        onClick={() => setShowPermissionHelp(false)}
                        className="flex-1 px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
                      >
                        Cancelar
                      </button>
                      <button
                        onClick={() => {
                          setShowPermissionHelp(false);
                          startCamera();
                        }}
                        className="flex-1 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors"
                      >
                        Reintentar
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Área de cámara/preview */}
            {!photoPreview ? (
              <div className="relative">
                {!isCameraActive ? (
                  // Botón para iniciar cámara
                  <div className="flex flex-col items-center">
                    <button
                      type="button"
                      onClick={startCamera}
                      className={`flex flex-col items-center justify-center w-full h-64 border-2 border-dashed rounded-lg transition-colors ${
                        errors.photo
                          ? 'border-red-400 bg-red-50 hover:bg-red-100'
                          : 'border-gray-300 bg-gray-50 hover:bg-gray-100'
                      }`}
                    >
                      <svg className={`w-16 h-16 mb-4 ${errors.photo ? 'text-red-400' : 'text-gray-400'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                      </svg>
                      <p className="text-lg font-semibold text-gray-700 mb-1">Tomar Foto</p>
                      <p className="text-sm text-gray-500">Haz clic para activar la cámara</p>
                    </button>
                    {cameraError && (
                      <p className="mt-3 text-sm text-red-500 text-center">{cameraError}</p>
                    )}
                  </div>
                ) : (
                  // Vista de cámara activa
                  <div className="flex flex-col items-center">
                    <div className="relative w-full max-w-sm mx-auto">
                      <video
                        ref={videoRef}
                        autoPlay
                        playsInline
                        muted
                        className="w-full h-80 object-cover rounded-lg border-4 border-blue-500 shadow-lg"
                        style={{ transform: 'scaleX(-1)' }}
                      />
                      {/* Guía de encuadre */}
                      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                        <div className="w-40 h-52 border-2 border-white border-dashed rounded-full opacity-50"></div>
                      </div>
                    </div>
                    <p className="mt-3 text-sm text-gray-600 text-center">Centra tu rostro dentro del óvalo</p>
                    <div className="flex gap-3 mt-4">
                      <button
                        type="button"
                        onClick={stopCamera}
                        className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-200 rounded-lg hover:bg-gray-300 transition-colors"
                      >
                        Cancelar
                      </button>
                      <button
                        type="button"
                        onClick={capturePhoto}
                        className="px-6 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2"
                      >
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                          <circle cx="12" cy="13" r="3" />
                        </svg>
                        Capturar
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              // Preview de foto capturada
              <div className="flex flex-col items-center">
                <div className="relative">
                  <img
                    src={photoPreview}
                    alt="Foto capturada"
                    className="w-48 h-60 object-cover rounded-lg border-4 border-green-500 shadow-lg"
                  />
                  <div className="absolute -top-2 -right-2 bg-green-500 rounded-full p-1">
                    <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                </div>
                <p className="mt-3 text-sm font-medium text-green-700">Foto capturada correctamente</p>
                <button
                  type="button"
                  onClick={handleRemovePhoto}
                  className="mt-3 inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-blue-600 bg-blue-50 rounded-lg hover:bg-blue-100 transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  Tomar otra foto
                </button>
              </div>
            )}

            {errors.photo && !isCameraActive && (
              <p className="mt-3 text-sm text-red-500 text-center">{errors.photo}</p>
            )}
          </div>
        </div>

        <div className="mt-8">
          <button
            onClick={handleContinueToExam}
            disabled={isCheckingStatus || isLoadingQuestions || isGeneratingRfc}
            className={`w-full py-4 font-semibold rounded-lg transition-colors ${
              isCheckingStatus || isLoadingQuestions || isGeneratingRfc
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-[#D91E18] text-white hover:bg-[#b81915]'
            }`}
          >
            {isGeneratingRfc ? 'Generando RFC...' : isCheckingStatus ? 'Verificando estatus...' : isLoadingQuestions ? 'Cargando preguntas...' : 'Continuar al Examen'}
          </button>
        </div>

        {/* Modal de confirmación de datos */}
        {showConfirmModal && (
          <div className="fixed inset-0 bg-black bg-opacity-60 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full max-h-[90vh] overflow-y-auto">
              <div className="p-6">
                {/* Header */}
                <div className="flex items-center mb-4">
                  <svg className="w-8 h-8 text-amber-500 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                  </svg>
                  <h3 className="text-xl font-bold text-gray-900">Confirma tus datos</h3>
                </div>

                {/* Resumen de datos */}
                <div className="bg-gray-50 rounded-lg p-4 mb-4">
                  <h4 className="text-sm font-semibold text-gray-700 mb-3">Datos registrados:</h4>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-500">Nombre:</span>
                      <span className="font-medium text-gray-900">{formData.nombres} {formData.primer_apellido} {formData.segundo_apellido}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">RFC:</span>
                      <span className="font-medium text-gray-900 uppercase">{formData.rfc_colaborador}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">CURP:</span>
                      <span className="font-medium text-gray-900">{curpData?.curp || '-'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">NSS:</span>
                      <span className="font-medium text-gray-900">{formData.nss}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Email:</span>
                      <span className="font-medium text-gray-900">{formData.email}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Proveedor:</span>
                      <span className="font-medium text-gray-900">{formData.proveedor}</span>
                    </div>
                  </div>
                </div>

                {/* Confirmación de veracidad */}
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
                  <p className="text-blue-800 font-semibold text-sm mb-2">Confirmaci&oacute;n de datos</p>
                  <p className="text-blue-700 text-sm">
                    Al continuar, confirmo que los datos proporcionados son correctos y corresponden a mi persona.
                    Esta informaci&oacute;n ser&aacute; utilizada para emitir mi certificaci&oacute;n de seguridad.
                  </p>
                </div>

                {/* Botones */}
                <div className="flex gap-3">
                  <button
                    onClick={() => setShowConfirmModal(false)}
                    className="flex-1 px-4 py-3 text-sm font-semibold text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors border border-gray-300"
                  >
                    Cancelar y Modificar
                  </button>
                  <button
                    onClick={handleConfirmAndProceed}
                    disabled={isCheckingStatus || isLoadingQuestions}
                    className={`flex-1 px-4 py-3 text-sm font-semibold rounded-lg transition-colors ${
                      isCheckingStatus || isLoadingQuestions
                        ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                        : 'bg-[#D91E18] text-white hover:bg-[#b81915]'
                    }`}
                  >
                    {isCheckingStatus ? 'Verificando...' : isLoadingQuestions ? 'Cargando...' : 'Confirmar y Continuar'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );

  // Renderizar paso 2: Examen con secciones (dinámico)
  const renderExamStep = () => {
    if (isLoadingQuestions || !examConfig) {
      return (
        <div className="max-w-4xl mx-auto text-center py-16">
          <svg className="animate-spin h-12 w-12 text-[#D91E18] mx-auto mb-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <p className="text-gray-600 text-lg">Cargando preguntas del examen...</p>
        </div>
      );
    }

    const currentCatIndex = currentSection - 1;
    const currentCat = examCategories[currentCatIndex];
    if (!currentCat) return null;

    const currentSectionQuestions = getQuestionsForCategory(currentCat.id);
    const totalAnswered = Object.keys(answers).length;
    const colors = COLOR_MAP[currentCat.color] || COLOR_MAP.gray;
    const totalSections = examCategories.length;

    return (
      <div className="max-w-4xl mx-auto">
        {/* Navegación de secciones */}
        <div className="bg-white rounded-lg shadow-lg p-4 mb-6">
          <div className="flex flex-wrap justify-between items-center gap-4">
            {examCategories.map((cat, idx) => {
              const sIdx = idx + 1;
              const answeredCount = getAnsweredCountForCategory(cat.id);
              const isComplete = answeredCount === cat.questions_to_show;
              const isCurrent = currentSection === sIdx;
              const sColors = COLOR_MAP[cat.color] || COLOR_MAP.gray;

              return (
                <button
                  key={cat.id}
                  onClick={() => goToSection(sIdx)}
                  className={`flex-1 min-w-[120px] p-3 rounded-lg transition-all ${
                    isCurrent
                      ? `${sColors.bg} text-white`
                      : `${sColors.light} ${sColors.text} hover:opacity-80`
                  }`}
                >
                  <div className="text-sm font-medium">Sección {sIdx}</div>
                  <div className="text-xs opacity-80">{cat.name}</div>
                  <div className="text-xs mt-1">
                    {answeredCount}/{cat.questions_to_show} {isComplete && '✓'}
                  </div>
                </button>
              );
            })}
          </div>
          <div className="mt-4 text-center text-sm text-gray-600">
            Total: {totalAnswered} / {totalExpectedQuestions} preguntas respondidas
          </div>
        </div>

        {/* Contenido de la sección actual */}
        <div className="bg-white rounded-lg shadow-lg p-8">
          <div className={`${colors.light} ${colors.border} border rounded-lg p-4 mb-6`}>
            <h2 className={`text-xl font-bold ${colors.text}`}>
              Sección {currentSection}: {currentCat.name}
            </h2>
            <p className="text-gray-600 text-sm mt-1">
              {currentCat.questions_to_show} preguntas de esta sección
            </p>
            <p className={`text-sm mt-2 ${colors.text}`}>
              <strong>Importante:</strong> Debes obtener mínimo {currentCat.min_score_percent}% en esta sección.
            </p>
          </div>

          <div className="space-y-8">
            {currentSectionQuestions.map((q, index) => (
              <div key={q.id} className="border-b border-gray-200 pb-6 last:border-0">
                <p className="font-medium text-gray-900 mb-4">
                  <span className={`${colors.text} font-bold`}>{index + 1}.</span> {q.question_text}
                </p>
                <div className="space-y-3">
                  {q.options.map((option, optIndex) => (
                    <label
                      key={optIndex}
                      className={`flex items-center p-4 border rounded-lg cursor-pointer transition-all ${
                        answers[q.id] === option
                          ? `${colors.border} ${colors.light}`
                          : 'border-gray-200 hover:border-gray-300'
                      }`}
                    >
                      <input
                        type="radio"
                        name={`question_${q.id}`}
                        value={option}
                        checked={answers[q.id] === option}
                        onChange={() => handleAnswerSelect(q.id, option)}
                        className="w-4 h-4 text-[#D91E18] focus:ring-[#D91E18]"
                      />
                      <span className="ml-3 text-gray-700">{option}</span>
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Navegación entre secciones */}
          <div className="mt-8 flex flex-wrap gap-4">
            {currentSection > 1 && (
              <button
                onClick={() => goToSection(currentSection - 1)}
                className="flex-1 py-4 border border-gray-300 text-gray-700 font-semibold rounded-lg hover:bg-gray-50 transition-colors"
              >
                ← Sección Anterior
              </button>
            )}

            {currentSection < totalSections ? (
              <button
                onClick={() => goToSection(currentSection + 1)}
                className={`flex-1 py-4 font-semibold rounded-lg transition-colors ${colors.bg} text-white hover:opacity-90`}
              >
                Siguiente Sección →
              </button>
            ) : (
              <button
                onClick={handleSubmit}
                disabled={isSubmitting || totalAnswered < totalExpectedQuestions}
                className={`flex-1 py-4 font-semibold rounded-lg transition-colors ${
                  isSubmitting || totalAnswered < totalExpectedQuestions
                    ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                    : 'bg-[#D91E18] text-white hover:bg-[#b81915]'
                }`}
              >
                {isSubmitting ? 'Enviando...' : `Enviar Examen (${totalAnswered}/${totalExpectedQuestions})`}
              </button>
            )}
          </div>
        </div>
      </div>
    );
  };

  // Renderizar paso 3: Resultado
  const renderResultStep = () => {
    if (!result) return null;

    const approved = result.approved;
    const sections = result.sections || [];

    return (
      <div className="max-w-2xl mx-auto">
        <div className="bg-white rounded-lg shadow-lg p-8">
          {/* Icono y título principal */}
          <div className="text-center mb-8">
            <div className={`inline-flex items-center justify-center w-24 h-24 rounded-full mb-6 ${
              approved ? 'bg-green-100' : 'bg-red-100'
            }`}>
              {approved ? (
                <svg className="w-16 h-16 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              ) : (
                <svg className="w-16 h-16 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              )}
            </div>

            <h1 className={`text-4xl font-bold mb-2 ${approved ? 'text-green-600' : 'text-red-600'}`}>
              {approved ? '¡Felicidades!' : 'No Aprobado'}
            </h1>
            <p className="text-gray-600">{result.message}</p>
          </div>

          {/* Score general */}
          <div className="bg-gray-50 rounded-lg p-6 mb-6 text-center">
            <p className="text-5xl font-bold text-gray-900 mb-2">
              {result.overall_score?.toFixed(1)}%
            </p>
            <p className="text-gray-600">Promedio General</p>
          </div>

          {/* Resultados por sección */}
          <div className="mb-8">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Resultados por Sección</h3>
            <div className="space-y-4">
              {sections.map((section) => {
                const cat = examCategories[section.section_number - 1];
                const colors = COLOR_MAP[cat?.color] || COLOR_MAP.gray;

                return (
                  <div
                    key={section.section_number}
                    className={`p-4 rounded-lg border ${
                      section.approved ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'
                    }`}
                  >
                    <div className="flex justify-between items-center">
                      <div>
                        <span className={`inline-block px-2 py-1 rounded text-xs font-medium ${colors.bg} text-white mr-2`}>
                          Sección {section.section_number}
                        </span>
                        <span className="font-medium text-gray-900">{section.section_name}</span>
                      </div>
                      <div className="text-right">
                        <span className={`text-2xl font-bold ${section.approved ? 'text-green-600' : 'text-red-600'}`}>
                          {section.score}%
                        </span>
                        <p className="text-xs text-gray-500">
                          {section.correct_count}/{section.total_questions} correctas
                        </p>
                      </div>
                    </div>
                    <div className="mt-2">
                      <span className={`text-sm font-medium ${section.approved ? 'text-green-600' : 'text-red-600'}`}>
                        {section.approved ? '✓ Aprobada' : '✗ Reprobada (mínimo 80%)'}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Información de intentos */}
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-6">
            <p className="text-amber-800 text-sm">
              <strong>Intentos:</strong> {result.attempts_used} de 3 utilizados
              {result.can_retry && (
                <span className="ml-2">
                  (Te quedan {result.attempts_remaining} intento(s))
                </span>
              )}
            </p>
          </div>

          {/* Botones de acción */}
          <div className="flex flex-col gap-4">
            {result.can_retry && (
              <>
                <button
                  onClick={handleRetry}
                  className="w-full py-4 bg-[#D91E18] text-white font-semibold rounded-lg hover:bg-[#b81915] transition-colors"
                >
                  Intentar de Nuevo
                </button>
                <button
                  onClick={handleWatchVideo}
                  className="w-full py-4 border border-gray-300 text-gray-700 font-semibold rounded-lg hover:bg-gray-50 transition-colors"
                >
                  Ver Video de Capacitación Nuevamente
                </button>
              </>
            )}

            {!result.can_retry && !approved && result.attempts_used >= 3 && (
              <div className="text-center text-red-600 p-4 bg-red-50 rounded-lg">
                <p className="font-medium">Has agotado tus 3 intentos.</p>
                <p className="text-sm mt-1">Contacta al administrador para más información.</p>
              </div>
            )}

            {approved && (
              <>
                <div className="text-center text-green-600 p-4 bg-green-50 rounded-lg">
                  <p className="font-medium">Recibirás tu certificación por correo electrónico.</p>
                </div>

                <button
                  onClick={handleDownloadPDF}
                  disabled={isDownloadingPDF}
                  className={`w-full py-4 font-semibold rounded-lg transition-colors flex items-center justify-center gap-2 ${
                    isDownloadingPDF
                      ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                      : 'bg-[#093D53] text-white hover:bg-[#0b4d68]'
                  }`}
                >
                  {isDownloadingPDF ? (
                    <>
                      <svg className="animate-spin h-5 w-5 text-gray-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      Generando PDF...
                    </>
                  ) : (
                    <>
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      Descargar Certificado PDF
                    </>
                  )}
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    );
  };

  // Renderizar pantalla de bloqueo
  const renderBlockedScreen = () => (
    <div className="max-w-2xl mx-auto">
      <div className="bg-white rounded-lg shadow-lg p-8">
        <div className="text-center">
          {/* Icono de bloqueo */}
          <div className="inline-flex items-center justify-center w-24 h-24 rounded-full bg-red-100 mb-6">
            <svg className="w-16 h-16 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>

          <h1 className="text-3xl font-bold text-red-600 mb-4">
            Acceso Bloqueado
          </h1>

          <div className="bg-red-50 border border-red-200 rounded-lg p-6 mb-6">
            <p className="text-red-800 text-lg font-medium mb-2">
              {statusError || 'Has agotado tus 3 intentos.'}
            </p>
            <p className="text-red-700">
              Contacta al administrador para más información.
            </p>
          </div>

          <div className="bg-gray-50 rounded-lg p-6 mb-6">
            <h3 className="font-semibold text-gray-900 mb-3">Información de contacto:</h3>
            <p className="text-gray-600 mb-2">
              <strong>Correo:</strong> seguridad@entersys.mx
            </p>
            <p className="text-gray-600">
              <strong>RFC registrado:</strong> {formData.rfc_colaborador?.toUpperCase()}
            </p>
          </div>

          <button
            onClick={() => navigate('/curso-seguridad')}
            className="w-full py-4 border border-gray-300 text-gray-700 font-semibold rounded-lg hover:bg-gray-50 transition-colors"
          >
            Volver al Inicio
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <>
      <Helmet>
        <title>Examen de Certificación de Seguridad | FEMSA</title>
        <meta name="description" content="Complete el examen de certificación de seguridad industrial para obtener su acreditación." />
        <meta name="robots" content="noindex, nofollow" />
      </Helmet>

      <main className="min-h-screen flex flex-col bg-gradient-to-b from-gray-50 to-white">
        {/* Header */}
        <header className="bg-white shadow-sm py-6">
          <div className="max-w-4xl mx-auto px-4 flex items-center justify-between">
            <img src="/images/coca-cola-femsa-logo.png" alt="Coca-Cola FEMSA" className="h-20 md:h-24" />
            <div className="flex items-center space-x-2">
              {[1, 2, 3].map((step) => (
                <div
                  key={step}
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                    currentStep >= step
                      ? 'bg-[#D91E18] text-white'
                      : 'bg-gray-200 text-gray-500'
                  }`}
                >
                  {step}
                </div>
              ))}
            </div>
          </div>
        </header>

        {/* Hero */}
        <section className="bg-[#D91E18] text-white py-8">
          <div className="max-w-4xl mx-auto px-4 text-center">
            <h1 className="text-3xl font-bold mb-2">
              {isBlocked && 'Acceso Restringido'}
              {!isBlocked && currentStep === 1 && 'Registro de Datos'}
              {!isBlocked && currentStep === 2 && `Examen de Certificación - Sección ${currentSection}${examCategories[currentSection - 1] ? ': ' + examCategories[currentSection - 1].name : ''}`}
              {!isBlocked && currentStep === 3 && 'Resultado del Examen'}
            </h1>
            <p className="text-red-100">
              Certificación de Seguridad Industrial - Coca-Cola FEMSA
            </p>
            {currentStep === 2 && examCategories.length > 0 && (
              <p className="text-red-200 text-sm mt-2">
                {totalExpectedQuestions} preguntas en {examCategories.length} secciones | Mínimo {examCategories[0]?.min_score_percent || 80}% en cada sección para aprobar
              </p>
            )}
          </div>
        </section>

        {/* Content */}
        <div className="flex-1 py-12 px-4">
          {isBlocked && renderBlockedScreen()}
          {!isBlocked && currentStep === 1 && renderPersonalDataStep()}
          {!isBlocked && currentStep === 2 && renderExamStep()}
          {!isBlocked && currentStep === 3 && renderResultStep()}
        </div>

        {/* Footer */}
        <footer className="bg-gray-100 py-6">
          <div className="max-w-4xl mx-auto px-4 text-center">
            {/* Redes sociales */}
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
