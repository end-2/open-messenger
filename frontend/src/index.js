export function getFrontendStatus() {
  return {
    service: "open-messenger-frontend",
    status: "scaffolded"
  };
}

if (process.env.NODE_ENV !== "test") {
  console.log(getFrontendStatus());
}
