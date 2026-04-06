import React from 'react';
import { useLocation } from 'react-router-dom';

/**
 * Botón flotante de soporte (?) que abre el formulario de Smartsheet.
 * Visible en las páginas de onboarding.
 */
const SupportFloatButton = () => {
  const location = useLocation();

  const VISIBLE_ROUTES = [
    '/curso-seguridad',
    '/formulario-curso-seguridad',
    '/actualizar-perfil',
  ];

  const isVisibleRoute = VISIBLE_ROUTES.some(route =>
    location.pathname === route || location.pathname.startsWith(route + '/')
  );

  if (!isVisibleRoute) {
    return null;
  }

  const handleClick = () => {
    window.open(
      'https://app.smartsheet.com/b/form/f6a9b9f489264ee78b6e6dd1a272c25e',
      '_blank',
      'noopener,noreferrer'
    );
  };

  return (
    <div
      style={{
        position: 'fixed',
        bottom: '1.5rem',
        left: '1.5rem',
        zIndex: 9999,
        pointerEvents: 'auto',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '6px',
      }}
    >
      <button
        onClick={handleClick}
        aria-label="Solicitar soporte"
        title="Solicitar soporte"
        style={{
          width: '56px',
          height: '56px',
          backgroundColor: '#2563EB',
          borderRadius: '50%',
          border: 'none',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 4px 12px rgba(37, 99, 235, 0.4)',
          transition: 'all 0.2s ease',
          color: '#fff',
          fontSize: '28px',
          fontWeight: '700',
          lineHeight: 1,
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = 'scale(1.1)';
          e.currentTarget.style.backgroundColor = '#1D4ED8';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = 'scale(1)';
          e.currentTarget.style.backgroundColor = '#2563EB';
        }}
      >
        ?
      </button>
      <span
        onClick={handleClick}
        style={{
          fontSize: '11px',
          fontWeight: '600',
          color: '#2563EB',
          cursor: 'pointer',
          textAlign: 'center',
          lineHeight: 1.2,
          userSelect: 'none',
        }}
      >
        Solicitar<br />soporte
      </span>
    </div>
  );
};

export default SupportFloatButton;
