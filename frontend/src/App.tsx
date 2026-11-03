import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import Site from "./Site";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Site />
      </AuthProvider>
    </BrowserRouter>
  );
}
