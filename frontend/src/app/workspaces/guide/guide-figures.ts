import { Type } from '@angular/core';

import { GuidePipelineDiagram } from './pipeline-diagram';

/*
 * Figures a chapter can place with a line of its own reading
 * <!-- figure:NAME -->. Keys are the NAME; the content test fails a chapter
 * that names a figure missing here. Keep this a flat literal of
 * name: Component pairs, one per line.
 */
export const GUIDE_FIGURES: Record<string, Type<unknown>> = {
  pipeline: GuidePipelineDiagram,
};
