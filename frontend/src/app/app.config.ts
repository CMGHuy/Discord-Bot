import {
  ApplicationConfig,
  provideBrowserGlobalErrorListeners,
  provideZonelessChangeDetection,
} from '@angular/core';
import { provideRouter } from '@angular/router';

import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    // Spec v13 Decision 2. Angular 21 leaves zone.js out of the scaffold
    // rather than requiring this provider, so the app would be zoneless
    // without it -- it is here to make the choice explicit and to fail
    // loudly if someone reintroduces zone.js, which would otherwise
    // silently restore the change detection this design does not want.
    provideZonelessChangeDetection(),
    provideRouter(routes),
  ],
};
