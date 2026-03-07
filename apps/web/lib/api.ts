import axios from "axios";
import type { SimulationResponse, Variant } from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const client = axios.create({ baseURL: BASE_URL });

export async function fetchSimulation(
  scenario: string = "sunny_valley",
  variant: Variant = "base"
): Promise<SimulationResponse> {
  const { data } = await client.get<SimulationResponse>("/simulate", {
    params: { scenario, variant },
  });
  return data;
}

export async function fetchScenarios() {
  const { data } = await client.get("/scenarios");
  return data;
}
