import { useEffect } from 'react';

interface PageTitleProps {
  title: string;
  children: React.ReactNode;
}

export default function PageTitle({ title, children }: PageTitleProps) {
  useEffect(() => {
    document.title = `${title} | Sunbird AI API`;
  }, [title]);

  return <>{children}</>;
}
