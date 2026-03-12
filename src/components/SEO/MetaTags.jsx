import { Helmet } from 'react-helmet-async';

export default function MetaTags({ title, description, noIndex }) {
  return (
    <Helmet>
      {title && <title>{title}</title>}
      {description && <meta name="description" content={description} />}
      {noIndex && <meta name="robots" content="noindex, nofollow" />}
    </Helmet>
  );
}
