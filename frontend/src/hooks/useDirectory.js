import { useContext } from 'react';
import { DirectoryContext } from '../context/DirectoryContext.js';

export function useDirectory() {
  const ctx = useContext(DirectoryContext);
  if (!ctx) throw new Error('useDirectory must be used within DirectoryProvider');
  return ctx;
}
