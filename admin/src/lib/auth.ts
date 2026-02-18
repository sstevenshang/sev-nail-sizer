import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import bcrypt from "bcryptjs";
import { getDb, seedAdmin } from "./db";

// Seed default admin on first load
const defaultHash = bcrypt.hashSync("admin123", 10);
seedAdmin("admin@sev.com", defaultHash);

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [
    Credentials({
      name: "Credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) return null;
        const db = getDb();
        const user = db
          .prepare("SELECT * FROM admins WHERE email = ?")
          .get(credentials.email as string) as
          | { id: number; email: string; password_hash: string }
          | undefined;
        if (!user) return null;
        const valid = bcrypt.compareSync(
          credentials.password as string,
          user.password_hash
        );
        if (!valid) return null;
        return { id: String(user.id), email: user.email };
      },
    }),
  ],
  pages: {
    signIn: "/login",
  },
  session: { strategy: "jwt" },
  secret: process.env.NEXTAUTH_SECRET || "dev-secret-change-in-production",
});
