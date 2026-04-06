import React, { lazy, Suspense } from 'react';
import { Routes, Route } from 'react-router-dom';
import SupportFloatButton from './components/SupportFloatButton';

const CursoSeguridad = lazy(() => import('./pages/CursoSeguridad'));
const FormularioCursoSeguridad = lazy(() => import('./pages/FormularioCursoSeguridad'));
const CredencialKOF = lazy(() => import('./pages/CredencialKOF'));
const CertificacionSeguridad = lazy(() => import('./pages/CertificacionSeguridad'));
const ActualizarPerfil = lazy(() => import('./pages/ActualizarPerfil'));
const SoportePanel = lazy(() => import('./pages/SoportePanel'));
const ReenvioRapido = lazy(() => import('./pages/ReenvioRapido'));

const Loading = () => (
  <div className="min-h-screen flex items-center justify-center bg-gray-50">
    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-green-600"></div>
  </div>
);

export default function App() {
  return (
    <Suspense fallback={<Loading />}>
      <SupportFloatButton />
      <Routes>
        <Route path="/curso-seguridad" element={<CursoSeguridad />} />
        <Route path="/formulario-curso-seguridad" element={<FormularioCursoSeguridad />} />
        <Route path="/credencial-kof/:rfc" element={<CredencialKOF />} />
        <Route path="/certificacion-seguridad/:uuid" element={<CertificacionSeguridad />} />
        <Route path="/actualizar-perfil" element={<ActualizarPerfil />} />
        <Route path="/soporte-onboarding" element={<SoportePanel />} />
        <Route path="/onboarding-reenvio/:rfc" element={<ReenvioRapido />} />
        <Route path="/onboarding-reenvio" element={<ReenvioRapido />} />
        <Route path="*" element={
          <div className="min-h-screen flex items-center justify-center">
            <p className="text-gray-500">Ruta no encontrada</p>
          </div>
        } />
      </Routes>
    </Suspense>
  );
}
