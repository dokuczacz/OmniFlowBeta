import { compare } from "bcrypt-ts";
import NextAuth, { type DefaultSession } from "next-auth";
import type { DefaultJWT } from "next-auth/jwt";
import Credentials from "next-auth/providers/credentials";
import { DUMMY_PASSWORD } from "@/lib/constants";
import { createGuestUser, getUser } from "@/lib/db/queries";
import { authConfig } from "./auth.config";

export type UserType = "guest" | "regular";

declare module "next-auth" {
  interface Session extends DefaultSession {
    user: {
      id: string;
      type: UserType;
    } & DefaultSession["user"];
  }

  // biome-ignore lint/nursery/useConsistentTypeDefinitions: "Required"
  interface User {
    id?: string;
    email?: string | null;
    type: UserType;
  }
}

declare module "next-auth/jwt" {
  interface JWT extends DefaultJWT {
    id: string;
    type: UserType;
  }
}

const authDisabled = process.env.DISABLE_AUTH === "1";

type Handler = (request: Request) => Promise<Response> | Response;

const disabledHandler: Handler = () =>
  new Response("Auth disabled for MVP", { status: 503 });

let handlers: { GET: Handler; POST: Handler };
let auth: () => Promise<DefaultSession | null> | Promise<any>;
let signIn: (...args: any[]) => Promise<any>;
let signOut: (...args: any[]) => Promise<any>;

if (authDisabled) {
  handlers = { GET: disabledHandler, POST: disabledHandler };
  auth = async () => null;
  signIn = async () => {
    throw new Error("Auth disabled for MVP");
  };
  signOut = async () => {
    throw new Error("Auth disabled for MVP");
  };
} else {
  const nextAuth = NextAuth({
    ...authConfig,
    providers: [
      Credentials({
        credentials: {},
        async authorize({ email, password }: any) {
          const users = await getUser(email);

          if (users.length === 0) {
            await compare(password, DUMMY_PASSWORD);
            return null;
          }

          const [user] = users;

          if (!user.password) {
            await compare(password, DUMMY_PASSWORD);
            return null;
          }

          const passwordsMatch = await compare(password, user.password);

          if (!passwordsMatch) {
            return null;
          }

          return { ...user, type: "regular" };
        },
      }),
      Credentials({
        id: "guest",
        credentials: {},
        async authorize() {
          const [guestUser] = await createGuestUser();
          return { ...guestUser, type: "guest" };
        },
      }),
    ],
    callbacks: {
      jwt({ token, user }) {
        if (user) {
          token.id = user.id as string;
          token.type = user.type;
        }

        return token;
      },
      session({ session, token }) {
        if (session.user) {
          session.user.id = token.id;
          session.user.type = token.type;
        }

        return session;
      },
    },
  });

  handlers = nextAuth.handlers;
  auth = nextAuth.auth;
  signIn = nextAuth.signIn;
  signOut = nextAuth.signOut;
}

export const { GET, POST } = handlers;
export { auth, signIn, signOut };
