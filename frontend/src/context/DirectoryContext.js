import { createContext } from 'react';

// Split from DirectoryProvider.jsx so that file exports only a component (oxlint
// react/only-export-components fast-refresh rule).
export const DirectoryContext = createContext(null);
