// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * Routes pi's read, write, edit, and bash tools to the task container through
 * the taskbridge Relay (TASK_RELAY_URL). The tools resolve relative paths and
 * run commands in the task's working directory (TASK_WORKDIR).
 */
import {
  type ExtensionAPI,
  createBashToolDefinition,
  createEditToolDefinition,
  createReadToolDefinition,
  createWriteToolDefinition,
  defineTool,
} from '@earendil-works/pi-coding-agent';
import {Type} from '@earendil-works/pi-ai';
import {readFile} from 'node:fs/promises';
import http from 'node:http';
import {tmpdir} from 'node:os';
import path from 'node:path';

const RELAY = process.env.TASK_RELAY_URL ?? "";
const WORKDIR = process.env.TASK_WORKDIR ?? "/";
const MAX_EXEC_SEC = 600;
// Rungs 0 to 2 do not let the agent run ifcopenshell yet (a later rung does). The harness puts a stub package in a folder
// of the task container and names it here; every bash command starts with PYTHONPATH pointing at it, so `import
// ifcopenshell` raises there. The image and the grader's copy of the library are not touched.
const PYTHONPATH_PREFIX = process.env.TASK_PYTHONPATH_PREFIX ?? "";
// Rung 1 feeds the input files once, as initial context; a command that names one of them again is refused.
// The harness lists the file names and folders in TASK_INPUT_GUARD (a JSON array of substrings).
const GUARD: string[] = (() => {
	try {
		const v = JSON.parse(process.env.TASK_INPUT_GUARD ?? "[]");
		return Array.isArray(v) ? v.filter((x) => typeof x === "string" && x.length > 0) : [];
	} catch {
		return [];
	}
})();
export function guardedBy(command: string, guard: string[]): string | undefined {
	return guard.find((g) => command.includes(g));
}
const GUARD_MESSAGE =
	"INPUT_GUARD: refused. The input files were given to you once, as the first message of this conversation, " +
	"and cannot be opened again. Work from what you already have in context; your own files are still available.\n";
const IMAGES: Record<string, string> = {
	".png": "image/png",
	".jpg": "image/jpeg",
	".jpeg": "image/jpeg",
	".gif": "image/gif",
	".webp": "image/webp",
};

interface RelayResponse {
	ok?: boolean;
	error?: string;
	truncated?: boolean;
	size?: number;
	content_b64?: string;
	output?: string;
	timed_out?: boolean;
	exit_code: number;
}

function relay(route: string, body: object): Promise<RelayResponse> {
	const url = new URL(`${RELAY}/${route}`);
	const data = Buffer.from(JSON.stringify(body));
	return new Promise((resolve, reject) => {
		const req = http.request(
			{
				hostname: url.hostname,
				port: url.port,
				path: url.pathname,
				method: "POST",
				headers: { "Content-Type": "application/json", "Content-Length": data.length },
			},
			(res) => {
				const chunks: Buffer[] = [];
				res.on("data", (chunk) => chunks.push(chunk));
				res.on("end", () => {
					try {
						const out = JSON.parse(Buffer.concat(chunks).toString() || "{}") as RelayResponse;
						if (res.statusCode !== 200) reject(new Error(out.error ?? `relay answered ${res.statusCode}`));
						else if (out.ok === false) reject(new Error(out.error));
						else resolve(out);
					} catch (err) {
						reject(err);
					}
				});
			},
		);
		req.on("error", reject);
		req.end(data);
	});
}

function quote(s: string): string {
	return `'${s.replace(/'/g, `'\\''`)}'`;
}

/**
 * Wraps `tool` so relative paths (e.g., "../data.csv") resolve and commands
 * start in `workdir`.
 *
 * `pi` uses the cwd of the context passed to a tool (which defaults to pi's own
 * scratch directory), so the tool receives a derived context whose `cwd` is
 * `workdir`. `Object.create` preserves the context's other properties, which pi
 * reads lazily.
 */
// tslint:disable-next-line:no-any
export function inTask(tool: any, workdir: string): any {
	return {
		...tool,
		// tslint:disable-next-line:no-any
		execute: (id: string, params: unknown, signal: unknown, onUpdate: unknown, ctx: any) =>
			tool.execute(id, params, signal, onUpdate, ctx && Object.create(ctx, { cwd: { value: workdir } })),
	};
}

/**
 * Returns a bash call's time limit in seconds: pi's `timeout` when it is a
 * positive number (or numeric string), capped at `max`. Zero, a negative
 * number, or an omitted value returns `max`, since 0 represents "no limit" in
 * pi.
 */
export function execLimit(timeout: unknown, max: number): number {
	const seconds = typeof timeout === "string" && timeout.trim() !== "" ? Number(timeout) : timeout;
	const usable = typeof seconds === "number" && Number.isFinite(seconds) && seconds > 0;
	return usable ? Math.max(1, Math.ceil(Math.min(seconds, max))) : max;
}

/**
 * Formats `exec` output as shown by a bash call, appending a truncation notice
 * at the end when the evaluator cut the middle of the output.
 */
export function execOutput(output: string, truncated: boolean): string {
	const note = "\n[the output was over 100 KB, so its middle was cut; write it to a file and read that in parts]\n";
	return truncated ? output + note : output;
}

/**
 * Returns true if `p` is pi's own temporary log file holding a long command's
 * output (`<tmp>/pi-bash-<16 hex>.log`), which stays local to the harness.
 */
export function isLocalTemp(p: string, tmp: string): boolean {
	return path.dirname(p) === tmp && /^pi-[a-z]+-[0-9a-f]{16}\.log$/.test(path.basename(p));
}

/**
 * Registers taskbridge-backed read, write, edit, and bash tools on the pi
 * coding agent extension API.
 */
// tslint:disable-next-line:no-default-export
export default function registerTaskTools(pi: ExtensionAPI) {
	// pi saves a long command's output to a local temp file and points the model at it; reads of that file stay local.
	const isLocal = (p: string) => isLocalTemp(p, tmpdir());

	const readOp = async (p: string) => {
		if (isLocal(p)) return readFile(p);
		const r = await relay("read_file", { path: p });
		if (r.truncated) throw new Error(`${p} is ${r.size} bytes, over the 10 MB a read returns; use bash on it`);
		return Buffer.from(r.content_b64 ?? "", "base64");
	};
	const writeOp = async (p: string, content: string) => {
		await relay("write_file", { path: p, content_b64: Buffer.from(content).toString("base64") });
	};
	// No separate access check: readOp and writeOp report a missing or unwritable file, one round trip fewer.
	const access = async () => {};
	// tslint:disable-next-line:no-any
	const register = (tool: any) => pi.registerTool(inTask(tool, WORKDIR));

	register(
		createReadToolDefinition(WORKDIR, {
			// Pi shrinks images to 2000 x 2000 by default; the drawings are read at their original size (as in rungs 0 and 1).
			autoResizeImages: false,
			operations: {
				readFile: readOp,
				access,
				detectImageMimeType: async (p) => IMAGES[path.extname(p).toLowerCase()] ?? null,
			},
		}),
	);
	// The relay's write_file creates missing parent directories.
	register(createWriteToolDefinition(WORKDIR, { operations: { writeFile: writeOp, mkdir: async () => {} } }));
	register(createEditToolDefinition(WORKDIR, { operations: { readFile: readOp, writeFile: writeOp, access } }));
	register(
		createBashToolDefinition(WORKDIR, {
			operations: {
				exec: async (command, cwd, { onData, signal, timeout }) => {
					if (signal?.aborted) throw new Error("aborted");
					if (guardedBy(command, GUARD) !== undefined) {
						onData(Buffer.from(GUARD_MESSAGE));
						return { exitCode: 1 };
					}
					const limit = execLimit(timeout, MAX_EXEC_SEC);
					const shadow = PYTHONPATH_PREFIX ? "export PYTHONPATH=" + quote(PYTHONPATH_PREFIX) + ':"${PYTHONPATH:-}"\n' : "";
					const run = relay("exec", { command: `cd ${quote(cwd)} || exit 1\n${shadow}${command}`, timeout_sec: limit });
					// The relay cannot cancel an exec: an abort stops the wait, and the command runs on to its time limit.
					const abort = new Promise<never>((_, reject) =>
						signal?.addEventListener("abort", () => reject(new Error("aborted")), { once: true }),
					);
					const r = await Promise.race([run, abort]);
					const output = execOutput(r.output ?? "", Boolean(r.truncated));
					if (output) onData(Buffer.from(output));
					if (r.timed_out) throw new Error(`timeout:${limit}`);
					return { exitCode: r.exit_code };
				},
			},
		}),
	);

	// Rung 3: the evaluation engine. Both tools call the harness (serve side), which holds the checks the check-builder wrote.
	const evaluate = defineTool({
		name: "evaluate",
		label: "Evaluate",
		description:
			"Evaluate your design with the project's fixed checks. Give the path of the IFC file you wrote, and optionally a shell " +
			"command that builds it (for example 'python solution.py'); the command runs first, with ifcopenshell available. " +
			"The reply validates the IFC schema, runs every check on the elements, and says for each failure where it is, by how much, " +
			"and what to change. Failures with one cause are listed once with a count. Call it after every build.",
		parameters: Type.Object({
			ifc: Type.String({ description: "Path of the IFC file to evaluate, inside the task container" }),
			run: Type.Optional(Type.String({ description: "Shell command that (re)builds the IFC first, run in the working directory" })),
		}),
		async execute(_id: string, params: { ifc: string; run?: string }) {
			const r = await relay("evaluate", params);
			return { content: [{ type: "text", text: r.output ?? "" }], details: {} };
		},
	});
	const concern = defineTool({
		name: "note_concern",
		label: "Note concern",
		description:
			"Record that one of the fixed checks seems wrong, too strict, too lax or missing (the checks cannot be edited). " +
			"Say which check and why. The concern is kept with the evaluation report and read by whoever reviews the result.",
		parameters: Type.Object({
			check: Type.String({ description: "Id of the check, or 'missing' for a check that should exist" }),
			text: Type.String({ description: "What is wrong and your evidence" }),
		}),
		async execute(_id: string, params: { check: string; text: string }) {
			const r = await relay("concern", params);
			return { content: [{ type: "text", text: r.output ?? "" }], details: {} };
		},
	});
	if (process.env.TASK_ENGINE === "1") {
		pi.registerTool(evaluate);
		pi.registerTool(concern);
	}

	pi.on("before_agent_start", (event) => {
		event.systemPromptOptions.cwd = WORKDIR;
	});
}
