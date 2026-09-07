import { createContext } from 'react';

// Split from EventSocketProvider.jsx so that file exports only a component (oxlint
// react/only-export-components fast-refresh rule).
export const EventSocketContext = createContext(null);
