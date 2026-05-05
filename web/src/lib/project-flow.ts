import type { Project } from './projects-store';

export type Phase = 'upload' | 'subtitle' | 'config' | 'generate';

export const PHASES: Phase[] = ['upload', 'subtitle', 'config', 'generate'];

export function isPhase(value: unknown): value is Phase {
  return typeof value === 'string' && (PHASES as string[]).includes(value);
}

/**
 * currentStep 表示“用户上次停留的页面”。
 * 不再根据资源自动跳页；缺什么资源，由当前页面自己显示提示和按钮。
 */
export function normalizePhase(project?: Pick<Project, 'currentStep'> | null, fallback: Phase = 'upload'): Phase {
  if (project && isPhase(project.currentStep)) return project.currentStep;
  return fallback;
}

/**
 * 兼容旧调用：现在任何步骤都可进入，页面内部负责显示缺失状态。
 */
export function canEnterPhase(_project: Project | null | undefined, _next: Phase): boolean {
  return true;
}

export function previousPhase(phase: Phase): Phase | null {
  const index = PHASES.indexOf(phase);
  if (index <= 0) return null;
  return PHASES[index - 1];
}

export function nextPhase(phase: Phase): Phase | null {
  const index = PHASES.indexOf(phase);
  if (index < 0 || index >= PHASES.length - 1) return null;
  return PHASES[index + 1];
}

export function hasVideo(project?: Pick<Project, 'uploadedVideoPath' | 'videoUrl'> | null): boolean {
  return Boolean(project?.uploadedVideoPath && project?.videoUrl);
}

export function hasSubtitle(project?: Pick<Project, 'uploadedSubtitlePath'> | null): boolean {
  return Boolean(project?.uploadedSubtitlePath);
}
